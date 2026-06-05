/*
 * fenet_hal.h - OpenPLC v4 I/O driver: LS XGT/XGB FEnet master (TCP 2004).
 *
 * Reference C++ port of the PROVEN pure-Python adapter app/comms/fenet_xgt.py.
 * The wire frames produced here MUST be byte-identical to that adapter; the
 * contract is machine-checked by tests/test_openplc_driver_parity.py.
 *
 * !!! NOT COMPILED in this repo (no OpenPLC v4 source / C toolchain here).
 *     Build & verify inside a real fork of Autonomy-Logic/openplc-runtime.    !!!
 *
 * Framing (XGT Dedicated Protocol):
 *   ADU = Application Header (20 bytes) + Command Block.
 *   Application header multibyte fields are little-endian (LE); the command
 *   block is also LE. (The brief's "header BE" note refers only to the textual
 *   convention for the 2-byte subheader/serial in MELSEC; the LS XGT *numeric*
 *   header fields here are LE, matching fenet_xgt.py's struct "<10sHBBHHB".)
 *
 *   Header (20B):
 *     off  0  Company ID    10  "LSIS-XGT\0\0"
 *     off 10  PLC Info       2  reserved 0x0000
 *     off 12  CPU Info       1  0x00
 *     off 13  Source         1  0x33 request / 0x11 response
 *     off 14  Invoke ID      2  LE, per-request counter (txn id)
 *     off 16  Length         2  LE, command-block byte count
 *     off 18  FEnet Pos      1  module slot (0)
 *     off 19  BCC            1  sum(header[0..18]) & 0xFF
 *
 *   Command block (LE):
 *     Command   2  0x0054 read-req / 0x0058 write-req
 *     DataType  2  0x0000 bit / 0x0002 word
 *     Reserved  2  0x0000
 *     BlockCnt  2  number of variable blocks (1..16)
 *     per read block:  NameLen 2 + Name (ASCII "%MX0"/"%MW100")
 *     per write block: (names first) NameLen 2 + Name, then (data) DataLen 2 + Data
 */

#ifndef OPENPLC_DRIVER_FENET_HAL_H
#define OPENPLC_DRIVER_FENET_HAL_H

#include <cstdint>
#include <string>
#include <vector>

namespace openplc_driver {
namespace fenet {

// ---- protocol constants (mirror fenet_xgt.py) --------------------------- //
constexpr uint8_t  SRC_CLIENT   = 0x33;
constexpr uint8_t  SRC_SERVER   = 0x11;
constexpr uint16_t CMD_READ_REQ  = 0x0054;
constexpr uint16_t CMD_WRITE_REQ = 0x0058;
constexpr uint16_t CMD_READ_RESP  = 0x0055;
constexpr uint16_t CMD_WRITE_RESP = 0x0059;
constexpr uint16_t DT_BIT  = 0x0000;
constexpr uint16_t DT_WORD = 0x0002;
constexpr int      HEADER_LEN     = 20;
constexpr int      DEFAULT_PORT   = 2004;
constexpr int      MAX_BLOCKS     = 16;

// ---- device map: PLC process-image slot <-> LS device name -------------- //
// kind: BIT writes/reads %MX bit devices; WORD writes/reads %MW word devices.
enum class Kind { Bit, Word };

struct DevMapEntry {
    // Process-image location in the OpenPLC v4 buffers.
    // For bits: bool_input[byte][bit] / bool_output[byte][bit].
    // For words: int_input[index] / int_output[index].
    int      byte;     // bit-buffer byte index   (Kind::Bit only)
    int      bit;      // bit-buffer bit index     (Kind::Bit only)
    int      word_idx; // int-buffer index         (Kind::Word only)
    Kind     kind;
    bool     is_input; // true  -> %IX/%IW image (driver READS PLC -> image)
                       // false -> %QX/%QW image (driver WRITES image -> PLC)
    std::string device; // LS device name, e.g. "%MX0", "%MW100"
};

// ---- frame builders (byte-identical to fenet_xgt.py) -------------------- //
uint8_t bcc(const uint8_t* header_first19);
std::vector<uint8_t> build_header(uint16_t payload_len, uint16_t invoke_id,
                                  uint8_t source = SRC_CLIENT);
std::vector<uint8_t> build_read_request(uint16_t data_type,
                                        const std::vector<std::string>& names);
std::vector<uint8_t> build_write_request(
    uint16_t data_type,
    const std::vector<std::pair<std::string, std::vector<uint8_t>>>& items);
std::vector<uint8_t> frame(const std::vector<uint8_t>& payload,
                           uint16_t invoke_id, uint8_t source = SRC_CLIENT);

// ---- OpenPLC v4 plugin ABI ---------------------------------------------- //
// Symbol names/signatures per the v4 core/src/drivers/README.md:
//   int  init(void *args);   // ONLY init takes the args struct
//   void start_loop(void);   void stop_loop(void);   void cleanup(void);
//   void cycle_start(void);  void cycle_end(void);    // native plugins only
// IMPORTANT (v4 contract): the `args` pointer is freed after init() returns,
// so init() MUST COPY the struct contents (we copy into g_args_copy), never
// store the pointer. Buffer access is guarded via args->mutex_take/mutex_give
// on args->buffer_mutex (a pthread_mutex_t*), NOT a C++ std::mutex.
extern "C" {
    int  init(void* args);     // configure socket + device map, copy args
    void start_loop(void);     // optional background thread hook
    void stop_loop(void);
    void cleanup(void);
    void cycle_start(void);    // FEnet read  -> *_input image
    void cycle_end(void);      // *_output image -> FEnet write
}

// ---- OpenPLC v3-compat callback HAL (blank.cpp shape) ------------------- //
// Provided so the same source can drop into a v3-style hardware layer.
extern "C" {
    void initializeHardware();
    void finalizeHardware();
    void updateBuffersIn();   // == cycle_start
    void updateBuffersOut();  // == cycle_end
}

}  // namespace fenet
}  // namespace openplc_driver

#endif  // OPENPLC_DRIVER_FENET_HAL_H
