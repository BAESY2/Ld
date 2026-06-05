/*
 * melsec_hal.cpp - OpenPLC v4 I/O driver: Mitsubishi MELSEC MC 3E binary master.
 *
 * Reference C++ port of app/comms/melsec.py (the PROVEN frame logic). Every
 * frame this file emits is asserted byte-for-byte against that Python adapter
 * by tests/test_openplc_driver_parity.py.
 *
 * !!! NOT COMPILED HERE. No OpenPLC v4 source / C++ toolchain in this repo.
 *     Drop into a fork of Autonomy-Logic/openplc-runtime under
 *     core/src/drivers/, wire up the real runtime-args struct, build with
 *     CMake, and verify against a CPU/GX Works + Wireshark. See README.md.    !!!
 */

#include "melsec_hal.h"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <mutex>
#include <stdexcept>

#if defined(__unix__) || defined(__APPLE__)
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace openplc_driver {
namespace melsec {

namespace {
inline void put_u16le(std::vector<uint8_t>& out, uint16_t v) {
    out.push_back(static_cast<uint8_t>(v & 0xFF));
    out.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
}
inline uint16_t get_u16le(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

// Device code table (mirrors melsec.py DEVICE_CODES). Order: longest prefix
// first so "SM"/"CS" win over "S"/"C". Pairs of {prefix, code, hex_numbering}.
struct DevDef { const char* prefix; uint8_t code; bool hex; };
const DevDef kDevices[] = {
    {"SM", 0x91, true},  {"SD", 0xA9, true},  {"TS", 0xC1, false},
    {"TC", 0xC0, false}, {"TN", 0xC2, false}, {"CS", 0xC4, false},
    {"CC", 0xC3, false}, {"CN", 0xC5, false}, {"X", 0x9C, true},
    {"Y", 0x9D, true},   {"M", 0x90, false},  {"L", 0x92, false},
    {"F", 0x93, false},  {"V", 0x94, false},  {"B", 0xA0, true},
    {"D", 0xA8, false},  {"W", 0xB4, true},   {"R", 0xAF, false},
    {"Z", 0xCC, false},
};
}  // namespace

Device parse_device(const std::string& device) {
    std::string s;
    for (char c : device)
        if (!std::isspace(static_cast<unsigned char>(c)))
            s.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    if (s.empty()) throw std::invalid_argument("empty device string");

    // Match the longest applicable prefix.
    const DevDef* best = nullptr;
    size_t best_len = 0;
    for (const auto& d : kDevices) {
        size_t plen = std::strlen(d.prefix);
        if (s.size() >= plen && s.compare(0, plen, d.prefix) == 0 &&
            plen > best_len) {
            best = &d;
            best_len = plen;
        }
    }
    if (!best) throw std::invalid_argument("unknown device prefix: " + device);

    std::string num = s.substr(best_len);
    if (num.empty()) throw std::invalid_argument("missing device number: " + device);
    int base = best->hex ? 16 : 10;
    size_t consumed = 0;
    unsigned long head = std::stoul(num, &consumed, base);
    if (consumed != num.size())
        throw std::invalid_argument("bad device number: " + device);
    if (head > 0xFFFFFF)
        throw std::invalid_argument("device number out of range: " + device);
    return Device{best->code, static_cast<uint32_t>(head)};
}

std::vector<uint8_t> pack_bits_nibble(const std::vector<bool>& values) {
    size_t n_bytes = (values.size() + 1) / 2;
    std::vector<uint8_t> out(n_bytes, 0);
    for (size_t i = 0; i < values.size(); ++i) {
        if (values[i]) {
            int shift = (i % 2 == 0) ? 4 : 0;
            out[i / 2] |= static_cast<uint8_t>(1 << shift);
        }
    }
    return out;
}

std::vector<bool> unpack_bits_nibble(const std::vector<uint8_t>& data,
                                     size_t count) {
    std::vector<bool> result;
    result.reserve(count);
    for (size_t i = 0; i < count; ++i) {
        uint8_t byte = data[i / 2];
        uint8_t nib = (i % 2 == 0) ? (byte >> 4) : (byte & 0x0F);
        result.push_back((nib & 0x01) != 0);
    }
    return result;
}

std::vector<uint8_t> request_prefix(uint16_t command, uint16_t subcommand,
                                    uint8_t device_code, uint32_t head,
                                    uint16_t count) {
    std::vector<uint8_t> out;
    put_u16le(out, command);
    put_u16le(out, subcommand);
    out.push_back(device_code);
    // head as 3-byte LE.
    out.push_back(static_cast<uint8_t>(head & 0xFF));
    out.push_back(static_cast<uint8_t>((head >> 8) & 0xFF));
    out.push_back(static_cast<uint8_t>((head >> 16) & 0xFF));
    put_u16le(out, count);
    return out;
}

std::vector<uint8_t> build_request(const std::vector<uint8_t>& request_data) {
    // length = monitoring timer (2) + request_data.
    uint16_t length = static_cast<uint16_t>(2 + request_data.size());
    std::vector<uint8_t> out;
    // subheader big-endian -> 50 00
    out.push_back(static_cast<uint8_t>((SUBHEADER_REQUEST >> 8) & 0xFF));
    out.push_back(static_cast<uint8_t>(SUBHEADER_REQUEST & 0xFF));
    out.push_back(NETWORK_NO);
    out.push_back(PC_NO);
    put_u16le(out, DEST_MODULE_IO);
    out.push_back(DEST_STATION);
    put_u16le(out, length);
    put_u16le(out, MONITORING_TIMER);
    out.insert(out.end(), request_data.begin(), request_data.end());
    return out;
}

// ------------------------------------------------------------------------- //
// v4 runtime-args shim (REPLACE with the real v4 header on integration).    //
// Field names match core/src/drivers/README.md. On integration delete this   //
// and #include the real header (IEC_BOOL/IEC_UINT, pthread_mutex_t*).        //
// ------------------------------------------------------------------------- //
#if !defined(OPENPLC_V4_HEADERS)
extern "C" {
typedef struct {
    uint8_t  (*bool_input)[8];
    uint8_t  (*bool_output)[8];
    uint16_t* int_input;
    uint16_t* int_output;
    int (*mutex_take)(void* mutex);
    int (*mutex_give)(void* mutex);
    void* buffer_mutex;
    int   buffer_size;
    int   bits_per_buffer;
} plugin_runtime_args_t;
}
#endif

// ------------------------------------------------------------------------- //
// Minimal blocking MC 3E binary client.                                     //
// ------------------------------------------------------------------------- //
class MelsecClient {
public:
    void configure(const std::string& host, int port) {
        host_ = host;
        port_ = port;
    }

    bool connect() {
#if defined(__unix__) || defined(__APPLE__)
        if (fd_ >= 0) return true;
        int fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return false;
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<uint16_t>(port_));
        if (::inet_pton(AF_INET, host_.c_str(), &addr.sin_addr) != 1) {
            ::close(fd);
            return false;
        }
        if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
            ::close(fd);
            return false;
        }
        int one = 1;
        ::setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
        fd_ = fd;
        return true;
#else
        return false;
#endif
    }

    void close() {
#if defined(__unix__) || defined(__APPLE__)
        if (fd_ >= 0) {
            ::close(fd_);
            fd_ = -1;
        }
#endif
    }

    std::vector<bool> read_bits(const std::string& device, uint16_t count) {
        Device d = parse_device(device);
        auto req = request_prefix(CMD_BATCH_READ, SUBCMD_BIT, d.code, d.head, count);
        std::vector<uint8_t> data;
        if (!transaction(req, data)) return {};
        return unpack_bits_nibble(data, count);
    }

    bool write_bits(const std::string& device, const std::vector<bool>& vals) {
        Device d = parse_device(device);
        auto req = request_prefix(CMD_BATCH_WRITE, SUBCMD_BIT, d.code, d.head,
                                  static_cast<uint16_t>(vals.size()));
        auto packed = pack_bits_nibble(vals);
        req.insert(req.end(), packed.begin(), packed.end());
        std::vector<uint8_t> data;
        return transaction(req, data);
    }

    bool write_words(const std::string& device,
                     const std::vector<uint16_t>& vals) {
        Device d = parse_device(device);
        auto req = request_prefix(CMD_BATCH_WRITE, SUBCMD_WORD, d.code, d.head,
                                  static_cast<uint16_t>(vals.size()));
        for (uint16_t v : vals) put_u16le(req, v);
        std::vector<uint8_t> data;
        return transaction(req, data);
    }

private:
#if defined(__unix__) || defined(__APPLE__)
    bool recv_exact(uint8_t* buf, size_t n) {
        size_t got = 0;
        while (got < n) {
            ssize_t r = ::recv(fd_, buf + got, n - got, 0);
            if (r <= 0) return false;
            got += static_cast<size_t>(r);
        }
        return true;
    }
    bool send_all(const std::vector<uint8_t>& data) {
        size_t sent = 0;
        while (sent < data.size()) {
            ssize_t r = ::send(fd_, data.data() + sent, data.size() - sent, 0);
            if (r <= 0) return false;
            sent += static_cast<size_t>(r);
        }
        return true;
    }
#endif

    // Send request data; return response data after the end code (which must be 0).
    bool transaction(const std::vector<uint8_t>& request_data,
                     std::vector<uint8_t>& out_data) {
#if defined(__unix__) || defined(__APPLE__)
        if (!connect()) return false;
        if (!send_all(build_request(request_data))) {
            close();
            return false;
        }
        uint8_t head[RESP_HEADER_LEN];
        if (!recv_exact(head, RESP_HEADER_LEN)) {
            close();
            return false;
        }
        uint16_t subheader =
            (static_cast<uint16_t>(head[0]) << 8) | head[1];
        if (subheader != SUBHEADER_RESPONSE) return false;
        uint16_t resp_len = get_u16le(head + 7);
        if (resp_len < 2) return false;
        std::vector<uint8_t> body(resp_len);
        if (!recv_exact(body.data(), resp_len)) {
            close();
            return false;
        }
        uint16_t end_code = get_u16le(body.data());
        if (end_code != 0x0000) return false;
        out_data.assign(body.begin() + 2, body.end());
        return true;
#else
        (void)request_data;
        (void)out_data;
        return false;
#endif
    }

    std::string host_ = "127.0.0.1";
    int port_ = DEFAULT_PORT;
    int fd_ = -1;
};

// ------------------------------------------------------------------------- //
// Driver state + device map.                                                //
// ------------------------------------------------------------------------- //
namespace {
MelsecClient g_client;
std::vector<DevMapEntry> g_devmap;
// v4 frees the args pointer after init(), so keep a COPY, not the pointer.
plugin_runtime_args_t g_args_copy{};
bool g_args_valid = false;

inline void buffers_lock() {
    if (g_args_valid && g_args_copy.mutex_take && g_args_copy.buffer_mutex)
        g_args_copy.mutex_take(g_args_copy.buffer_mutex);
}
inline void buffers_unlock() {
    if (g_args_valid && g_args_copy.mutex_give && g_args_copy.buffer_mutex)
        g_args_copy.mutex_give(g_args_copy.buffer_mutex);
}

// EDIT THIS for your PLC. Inputs: driver reads PLC -> *_input image.
// Outputs: driver reads *_output image -> writes PLC.
void load_device_map() {
    if (!g_devmap.empty()) return;
    for (int i = 0; i < 8; ++i)
        g_devmap.push_back(DevMapEntry{0, i, 0, Kind::Bit, true,
                                       "M" + std::to_string(i)});
    for (int i = 0; i < 8; ++i)
        g_devmap.push_back(DevMapEntry{0, i, 0, Kind::Bit, false,
                                       "M" + std::to_string(1000 + i)});
    g_devmap.push_back(DevMapEntry{0, 0, 0, Kind::Word, false, "D100"});
}

void set_input_bit(int byte, int bit, bool v) {
    if (!g_args_valid || !g_args_copy.bool_input) return;
    g_args_copy.bool_input[byte][bit] = v ? 1 : 0;
}
bool get_output_bit(int byte, int bit) {
    if (!g_args_valid || !g_args_copy.bool_output) return false;
    return g_args_copy.bool_output[byte][bit] != 0;
}
}  // namespace

// ------------------------------------------------------------------------- //
// v4 plugin ABI.                                                            //
// ------------------------------------------------------------------------- //
extern "C" int init(void* args) {
    if (args) {
        g_args_copy = *static_cast<plugin_runtime_args_t*>(args);
        g_args_valid = true;
    }
    load_device_map();
    g_client.configure("127.0.0.1", DEFAULT_PORT);  // TODO: from plugins.conf
    return g_client.connect() ? 0 : -1;
}

extern "C" void start_loop(void) {}
extern "C" void stop_loop(void) {}

extern "C" void cleanup(void) {
    g_client.close();
    g_args_valid = false;
}

// MC batch-read mapped input bit devices -> *_input image. Each mapped device
// is read individually (1 point) so non-contiguous addresses stay safe; this
// matches MelsecPlcLink.read_outputs in melsec.py.
extern "C" void cycle_start(void) {
    if (!g_args_valid) return;
    for (const auto& e : g_devmap) {
        if (!e.is_input || e.kind != Kind::Bit) continue;
        std::vector<bool> bits = g_client.read_bits(e.device, 1);
        if (bits.empty()) continue;
        buffers_lock();
        set_input_bit(e.byte, e.bit, bits[0]);
        buffers_unlock();
    }
}

// *_output image -> MC batch-write. Snapshot under lock, then write.
extern "C" void cycle_end(void) {
    if (!g_args_valid) return;
    std::vector<std::pair<const DevMapEntry*, bool>> bit_writes;
    std::vector<std::pair<const DevMapEntry*, uint16_t>> word_writes;
    buffers_lock();
    for (const auto& e : g_devmap) {
        if (e.is_input) continue;
        if (e.kind == Kind::Bit)
            bit_writes.emplace_back(&e, get_output_bit(e.byte, e.bit));
        else if (g_args_copy.int_output)
            word_writes.emplace_back(&e, g_args_copy.int_output[e.word_idx]);
    }
    buffers_unlock();

    for (const auto& w : bit_writes)
        g_client.write_bits(w.first->device, {w.second});
    for (const auto& w : word_writes)
        g_client.write_words(w.first->device, {w.second});
}

// ------------------------------------------------------------------------- //
// v3-compat callback HAL (blank.cpp shape).                                 //
// ------------------------------------------------------------------------- //
extern "C" void initializeHardware() { init(nullptr); }
extern "C" void finalizeHardware() { cleanup(); }
extern "C" void updateBuffersIn() { cycle_start(); }
extern "C" void updateBuffersOut() { cycle_end(); }

}  // namespace melsec
}  // namespace openplc_driver
