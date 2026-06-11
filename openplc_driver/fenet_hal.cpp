/*
 * fenet_hal.cpp - OpenPLC v4 I/O driver: LS XGT/XGB FEnet master (TCP 2004).
 *
 * Reference C++ port of app/comms/fenet_xgt.py (the PROVEN frame logic).
 * Every frame this file emits is asserted byte-for-byte against that Python
 * adapter by tests/test_openplc_driver_parity.py.
 *
 * !!! NOT COMPILED HERE. There is no OpenPLC v4 source tree or C/C++ toolchain
 *     in this repo. Drop into a fork of Autonomy-Logic/openplc-runtime under
 *     core/src/drivers/, wire up the real runtime-args struct, then build with
 *     CMake and verify against a CPU/Wireshark. See README.md.                !!!
 *
 * --- v4 runtime-args shim -------------------------------------------------
 * The real v4 plugin loader passes a plugin_runtime_args_t* exposing the
 * process-image pointers and the buffer lock. Because the exact struct layout
 * lives in the (absent) v4 headers, we model the SUBSET we use behind a thin
 * shim. When integrating, replace plugin_runtime_args_t below with an include
 * of the real v4 header and delete this shim (the field names match v4).
 */

#include "fenet_hal.h"

#include <cstring>
#include <mutex>
#include <stdexcept>

// Sockets: POSIX. v4 runtime is Linux (SCHED_FIFO). Guarded so this file at
// least parses on non-POSIX while staying obviously Linux-targeted.
#if defined(__unix__) || defined(__APPLE__)
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace openplc_driver {
namespace fenet {

namespace {
constexpr char COMPANY_ID[8] = {'L', 'S', 'I', 'S', '-', 'X', 'G', 'T'};

inline void put_u16le(std::vector<uint8_t>& out, uint16_t v) {
    out.push_back(static_cast<uint8_t>(v & 0xFF));
    out.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
}
inline uint16_t get_u16le(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}
}  // namespace

// ------------------------------------------------------------------------- //
// Frame builders — mirror fenet_xgt.py exactly.                             //
// ------------------------------------------------------------------------- //
uint8_t bcc(const uint8_t* header_first19) {
    unsigned sum = 0;
    for (int i = 0; i < 19; ++i) sum += header_first19[i];
    return static_cast<uint8_t>(sum & 0xFF);
}

std::vector<uint8_t> build_header(uint16_t payload_len, uint16_t invoke_id,
                                  uint8_t source) {
    // struct.pack("<10sHBBHHB", "LSIS-XGT\0\0", 0, 0, source, invoke, len, 0)
    std::vector<uint8_t> h;
    h.reserve(HEADER_LEN);
    for (int i = 0; i < 8; ++i) h.push_back(static_cast<uint8_t>(COMPANY_ID[i]));
    h.push_back(0x00);  // company NUL pad 1
    h.push_back(0x00);  // company NUL pad 2  (10s field complete)
    put_u16le(h, 0x0000);          // PLC info (reserved)
    h.push_back(0x00);             // CPU info
    h.push_back(source);           // source of frame
    put_u16le(h, invoke_id);       // invoke id (LE)
    put_u16le(h, payload_len);     // length (LE)
    h.push_back(0x00);             // FEnet position
    h.push_back(bcc(h.data()));    // BCC over header[0..18]
    return h;                      // 20 bytes
}

std::vector<uint8_t> build_read_request(uint16_t data_type,
                                        const std::vector<std::string>& names) {
    if (names.empty() || names.size() > static_cast<size_t>(MAX_BLOCKS))
        throw std::invalid_argument("block count out of range");
    std::vector<uint8_t> body;
    put_u16le(body, CMD_READ_REQ);
    put_u16le(body, data_type);
    put_u16le(body, 0x0000);  // reserved
    put_u16le(body, static_cast<uint16_t>(names.size()));
    for (const auto& name : names) {
        put_u16le(body, static_cast<uint16_t>(name.size()));
        body.insert(body.end(), name.begin(), name.end());
    }
    return body;
}

std::vector<uint8_t> build_write_request(
    uint16_t data_type,
    const std::vector<std::pair<std::string, std::vector<uint8_t>>>& items) {
    if (items.empty() || items.size() > static_cast<size_t>(MAX_BLOCKS))
        throw std::invalid_argument("block count out of range");
    std::vector<uint8_t> body;
    put_u16le(body, CMD_WRITE_REQ);
    put_u16le(body, data_type);
    put_u16le(body, 0x0000);  // reserved
    put_u16le(body, static_cast<uint16_t>(items.size()));
    // XGT individual-write layout: all name blocks first, then all data blocks.
    for (const auto& it : items) {
        put_u16le(body, static_cast<uint16_t>(it.first.size()));
        body.insert(body.end(), it.first.begin(), it.first.end());
    }
    for (const auto& it : items) {
        put_u16le(body, static_cast<uint16_t>(it.second.size()));
        body.insert(body.end(), it.second.begin(), it.second.end());
    }
    return body;
}

std::vector<uint8_t> frame(const std::vector<uint8_t>& payload,
                           uint16_t invoke_id, uint8_t source) {
    std::vector<uint8_t> out =
        build_header(static_cast<uint16_t>(payload.size()), invoke_id, source);
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}

// ------------------------------------------------------------------------- //
// v4 runtime-args shim (REPLACE with the real v4 header on integration).    //
//                                                                           //
// The real plugin_runtime_args_t lives in the (absent) v4 headers; field    //
// names below match core/src/drivers/README.md. On integration:             //
//   - delete this struct, #include the real v4 plugin header;               //
//   - IEC_BOOL/IEC_UINT replace uint8_t/uint16_t;                           //
//   - guard buffers with mutex_take(buffer_mutex)/mutex_give(buffer_mutex). //
// ------------------------------------------------------------------------- //
#if !defined(OPENPLC_V4_HEADERS)
extern "C" {
typedef struct {
    // bool_*[byte][bit] digital image; int_* are 16-bit word images.
    uint8_t  (*bool_input)[8];
    uint8_t  (*bool_output)[8];
    uint16_t* int_input;
    uint16_t* int_output;
    int (*mutex_take)(void* mutex);
    int (*mutex_give)(void* mutex);
    void* buffer_mutex;  // pthread_mutex_t* in real v4
    int   buffer_size;
    int   bits_per_buffer;
} plugin_runtime_args_t;
}
#endif

// ------------------------------------------------------------------------- //
// Minimal blocking FEnet client (one socket, per-request invoke id).        //
// ------------------------------------------------------------------------- //
class FenetClient {
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
        return false;  // non-POSIX: integrate on the Linux v4 runtime.
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

    // Read bit devices; returns one bool per name. Empty vector on failure.
    std::vector<bool> read_bits(const std::vector<std::string>& names) {
        std::vector<uint8_t> resp;
        if (!transaction(build_read_request(DT_BIT, names), resp)) return {};
        std::vector<std::vector<uint8_t>> blocks;
        if (!parse_read_blocks(resp, names.size(), blocks)) return {};
        std::vector<bool> out;
        out.reserve(blocks.size());
        for (const auto& b : blocks) out.push_back(!b.empty() && b[0] != 0);
        return out;
    }

    bool write_bit(const std::string& name, bool value) {
        std::vector<uint8_t> data{static_cast<uint8_t>(value ? 0x01 : 0x00)};
        std::vector<uint8_t> resp;
        return transaction(build_write_request(DT_BIT, {{name, data}}), resp);
    }

    bool write_word(const std::string& name, uint16_t value) {
        std::vector<uint8_t> data;
        put_u16le(data, value);
        std::vector<uint8_t> resp;
        return transaction(build_write_request(DT_WORD, {{name, data}}), resp);
    }

private:
    uint16_t next_invoke() {
        invoke_ = static_cast<uint16_t>((invoke_ + 1) & 0xFFFF);
        return invoke_;
    }

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

    // Send one command block, return the response command block (header stripped).
    bool transaction(const std::vector<uint8_t>& payload,
                     std::vector<uint8_t>& resp_body) {
#if defined(__unix__) || defined(__APPLE__)
        if (!connect()) return false;
        uint16_t invoke = next_invoke();
        if (!send_all(frame(payload, invoke, SRC_CLIENT))) {
            close();
            return false;
        }
        uint8_t head[HEADER_LEN];
        if (!recv_exact(head, HEADER_LEN)) {
            close();
            return false;
        }
        if (std::memcmp(head, COMPANY_ID, 8) != 0) return false;
        uint8_t source = head[13];
        uint16_t r_invoke = get_u16le(head + 14);
        uint16_t length = get_u16le(head + 16);
        if (source != SRC_SERVER || r_invoke != invoke) return false;
        resp_body.resize(length);
        if (length && !recv_exact(resp_body.data(), length)) {
            close();
            return false;
        }
        // error state at offset 6 of the command block (command,dtype,resv,err).
        if (resp_body.size() < 8) return false;
        uint16_t error_state = get_u16le(resp_body.data() + 6);
        return error_state == 0;
#else
        (void)payload;
        (void)resp_body;
        return false;
#endif
    }

    static bool parse_read_blocks(const std::vector<uint8_t>& body, size_t count,
                                  std::vector<std::vector<uint8_t>>& out) {
        // body: command(2) dtype(2) reserved(2) errstate(2) blockcnt(2) [blocks]
        if (body.size() < 10) return false;
        uint16_t block_count = get_u16le(body.data() + 8);
        if (block_count != count) return false;
        size_t off = 10;
        for (size_t i = 0; i < count; ++i) {
            if (off + 2 > body.size()) return false;
            uint16_t dcount = get_u16le(body.data() + off);
            off += 2;
            if (off + dcount > body.size()) return false;
            out.emplace_back(body.begin() + off, body.begin() + off + dcount);
            off += dcount;
        }
        return true;
    }

    std::string host_ = "127.0.0.1";
    int port_ = DEFAULT_PORT;
    int fd_ = -1;
    uint16_t invoke_ = 0;
};

// ------------------------------------------------------------------------- //
// Driver state.                                                             //
// ------------------------------------------------------------------------- //
namespace {
FenetClient g_client;
std::vector<DevMapEntry> g_devmap;  // populated by load_device_map()
// v4 frees the args pointer after init(), so we keep a COPY, not the pointer.
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

// EDIT THIS for your PLC: symbol slot -> LS device name.
// Inputs (is_input=true)  : driver READS the PLC and writes the *_input image.
// Outputs (is_input=false): driver READS the *_output image and WRITES the PLC.
void load_device_map() {
    if (!g_devmap.empty()) return;
    // Example: 8 input bits %MX0..%MX7 -> bool_input[0][0..7];
    //          8 output bits %MX16..%MX23 <- bool_output[0][0..7].
    for (int i = 0; i < 8; ++i)
        g_devmap.push_back(DevMapEntry{0, i, 0, Kind::Bit, true,
                                       "%MX" + std::to_string(i)});
    for (int i = 0; i < 8; ++i)
        g_devmap.push_back(DevMapEntry{0, i, 0, Kind::Bit, false,
                                       "%MX" + std::to_string(16 + i)});
    // Example word: %MW100 <- int_output[0].
    g_devmap.push_back(DevMapEntry{0, 0, 0, Kind::Word, false, "%MW100"});
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
// v4 plugin ABI entry points.                                               //
// ------------------------------------------------------------------------- //
extern "C" int init(void* args) {
    // v4 frees `args` after init() returns -> COPY the struct, never store ptr.
    if (args) {
        g_args_copy = *static_cast<plugin_runtime_args_t*>(args);
        g_args_valid = true;
    }
    load_device_map();
    // TODO: read host/port from the plugins.conf per-plugin config file.
    g_client.configure("127.0.0.1", DEFAULT_PORT);
    return g_client.connect() ? 0 : -1;
}

extern "C" void start_loop(void) {}
extern "C" void stop_loop(void) {}

extern "C" void cleanup(void) {
    g_client.close();
    g_args_valid = false;
}

// FEnet batch-read mapped input devices -> *_input process image.
extern "C" void cycle_start(void) {
    if (!g_args_valid) return;

    std::vector<std::string> bit_names;
    std::vector<const DevMapEntry*> bit_entries;
    for (const auto& e : g_devmap) {
        if (e.is_input && e.kind == Kind::Bit) {
            bit_names.push_back(e.device);
            bit_entries.push_back(&e);
        }
    }
    std::vector<bool> bits;
    if (!bit_names.empty()) bits = g_client.read_bits(bit_names);

    if (bits.size() == bit_entries.size()) {
        buffers_lock();
        for (size_t i = 0; i < bit_entries.size(); ++i)
            set_input_bit(bit_entries[i]->byte, bit_entries[i]->bit, bits[i]);
        buffers_unlock();
    }
    // Word inputs (int_input) would be read with DT_WORD here similarly.
}

// *_output process image -> FEnet batch-write mapped output devices.
extern "C" void cycle_end(void) {
    if (!g_args_valid) return;

    // Snapshot outputs under the lock, then do socket I/O without holding it.
    std::vector<std::pair<const DevMapEntry*, bool>> bit_writes;
    std::vector<std::pair<const DevMapEntry*, uint16_t>> word_writes;
    buffers_lock();
    for (const auto& e : g_devmap) {
        if (e.is_input) continue;
        if (e.kind == Kind::Bit) {
            bit_writes.emplace_back(&e, get_output_bit(e.byte, e.bit));
        } else if (g_args_copy.int_output) {
            word_writes.emplace_back(&e, g_args_copy.int_output[e.word_idx]);
        }
    }
    buffers_unlock();

    for (const auto& w : bit_writes) g_client.write_bit(w.first->device, w.second);
    for (const auto& w : word_writes)
        g_client.write_word(w.first->device, w.second);
}

// ------------------------------------------------------------------------- //
// v3-compat callback HAL (blank.cpp shape). v3 has no args struct; the       //
// runtime sets up the global buffers + bufferLock itself. These thin shims   //
// let the same source drop into a v3 hardware layer.                         //
// ------------------------------------------------------------------------- //
extern "C" void initializeHardware() { init(nullptr); }
extern "C" void finalizeHardware() { cleanup(); }
extern "C" void updateBuffersIn() { cycle_start(); }
extern "C" void updateBuffersOut() { cycle_end(); }

}  // namespace fenet
}  // namespace openplc_driver
