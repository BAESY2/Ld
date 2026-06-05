/*
 * melsec_hal.h - OpenPLC v4 I/O driver: Mitsubishi MELSEC MC protocol
 *                (SLMP 3E binary master, port configurable).
 *
 * Reference C++ port of the PROVEN pure-Python adapter app/comms/melsec.py.
 * Frames here MUST be byte-identical to that adapter; the contract is
 * machine-checked by tests/test_openplc_driver_parity.py.
 *
 * !!! NOT COMPILED in this repo. Build & verify inside a real fork of
 *     Autonomy-Logic/openplc-runtime.                                        !!!
 *
 * 3E binary request frame (all multibyte LE; subheader written big-endian as
 * the byte sequence 50 00 to match melsec.py's ">H" for the subheader only):
 *   off  0  Subheader        2  0x5000 -> bytes 50 00
 *   off  2  Network No       1  0x00
 *   off  3  PC No            1  0xFF
 *   off  4  Dest module IO   2  0x03FF (LE -> FF 03)
 *   off  6  Dest station     1  0x00
 *   off  7  Request data len 2  LE (monitoring timer .. end)
 *   off  9  Monitoring timer 2  LE 0x0010
 *   off 11  Command          2  LE 0x0401 batch-read / 0x1401 batch-write
 *   off 13  Subcommand       2  LE 0x0001 bit / 0x0000 word
 *   off 15  Device code      1  M=0x90, D=0xA8, ...
 *   off 16  Head device no   3  LE
 *   off 19  Device points    2  LE
 *   off 21  (write only) data ...
 *
 * Bit packing (subcommand 0x0001): 1 point = 1 nibble, 2 points/byte; even
 * point -> high nibble, odd point -> low nibble. Differs from Modbus LSB bytes.
 * Word packing (subcommand 0x0000): 1 point = 1 word = 2 bytes LE.
 */

#ifndef OPENPLC_DRIVER_MELSEC_HAL_H
#define OPENPLC_DRIVER_MELSEC_HAL_H

#include <cstdint>
#include <string>
#include <vector>

namespace openplc_driver {
namespace melsec {

constexpr uint16_t SUBHEADER_REQUEST  = 0x5000;
constexpr uint16_t SUBHEADER_RESPONSE = 0xD000;
constexpr uint8_t  NETWORK_NO   = 0x00;
constexpr uint8_t  PC_NO        = 0xFF;
constexpr uint16_t DEST_MODULE_IO = 0x03FF;
constexpr uint8_t  DEST_STATION = 0x00;
constexpr uint16_t MONITORING_TIMER = 0x0010;
constexpr uint16_t CMD_BATCH_READ  = 0x0401;
constexpr uint16_t CMD_BATCH_WRITE = 0x1401;
constexpr uint16_t SUBCMD_BIT  = 0x0001;
constexpr uint16_t SUBCMD_WORD = 0x0000;
constexpr int      RESP_HEADER_LEN = 9;
constexpr int      DEFAULT_PORT = 5007;  // MC has no fixed default; configure.

// parse_device("M0")/("D100")/("X10") -> (device_code, head_number).
// X/Y/B/W/SM/SD use hex numbering; M/L/D/T/C/R use decimal. Throws on bad input.
struct Device {
    uint8_t  code;
    uint32_t head;
};
Device parse_device(const std::string& device);

// Nibble bit packing (2 points/byte, even=high nibble).
std::vector<uint8_t> pack_bits_nibble(const std::vector<bool>& values);
std::vector<bool>    unpack_bits_nibble(const std::vector<uint8_t>& data,
                                        size_t count);

// 3E request-data builder (command .. points), and full framed request.
std::vector<uint8_t> request_prefix(uint16_t command, uint16_t subcommand,
                                    uint8_t device_code, uint32_t head,
                                    uint16_t count);
std::vector<uint8_t> build_request(const std::vector<uint8_t>& request_data);

// Device map: process-image slot <-> MELSEC device.
enum class Kind { Bit, Word };
struct DevMapEntry {
    int      byte;
    int      bit;
    int      word_idx;
    Kind     kind;
    bool     is_input;
    std::string device;  // "M0", "D100", ...
};

// ---- OpenPLC v4 plugin ABI ---------------------------------------------- //
// Per core/src/drivers/README.md: only init() takes the args struct, and that
// struct is freed after init() returns (so init MUST copy it). Buffer access
// goes through args->mutex_take/mutex_give on args->buffer_mutex.
extern "C" {
    int  init(void* args);     // copy args, configure socket + device map
    void start_loop(void);
    void stop_loop(void);
    void cleanup(void);
    void cycle_start(void);    // MC read  -> *_input image
    void cycle_end(void);      // *_output image -> MC write
}

// ---- v3-compat callback HAL --------------------------------------------- //
extern "C" {
    void initializeHardware();
    void finalizeHardware();
    void updateBuffersIn();
    void updateBuffersOut();
}

}  // namespace melsec
}  // namespace openplc_driver

#endif  // OPENPLC_DRIVER_MELSEC_HAL_H
