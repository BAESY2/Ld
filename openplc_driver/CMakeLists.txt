# ---------------------------------------------------------------------------
# OpenPLC v4 native driver build fragment — LS FEnet + Mitsubishi MELSEC.
#
# NOT a standalone build. This is a fragment to be include()'d from (or copied
# into) your fork's core/src/drivers/CMakeLists.txt. It builds two shared
# objects loaded by the v4 plugin loader as type=1 (native) plugins.
#
# The drivers #include the real v4 plugin header for plugin_runtime_args_t.
# Until you wire that up, the .cpp files provide a fallback shim struct guarded
# by `#if !defined(OPENPLC_V4_HEADERS)`. Define OPENPLC_V4_HEADERS and add the
# real include path once integrating so the shim is dropped.
#
# Equivalent one-liners (per the v4 drivers README) if you build by hand:
#   g++ -shared -fPIC -std=c++17 -I<openplc>/core/lib \
#       -o fenet_hal.so  fenet_hal.cpp  -lpthread
#   g++ -shared -fPIC -std=c++17 -I<openplc>/core/lib \
#       -o melsec_hal.so melsec_hal.cpp -lpthread
# ---------------------------------------------------------------------------

cmake_minimum_required(VERSION 3.13)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Where this fragment lives (adjust if you copy the .cpp/.h elsewhere).
set(KR_DRIVER_DIR ${CMAKE_CURRENT_LIST_DIR})

# Path to the v4 runtime headers that define plugin_runtime_args_t / IEC_*.
# Point this at <openplc-runtime>/core/lib (or wherever the plugin ABI header
# lives in your fork) and uncomment the OPENPLC_V4_HEADERS define below.
# set(OPENPLC_LIB_DIR ${CMAKE_SOURCE_DIR}/core/lib)

add_library(fenet_hal SHARED ${KR_DRIVER_DIR}/fenet_hal.cpp)
add_library(melsec_hal SHARED ${KR_DRIVER_DIR}/melsec_hal.cpp)

foreach(drv fenet_hal melsec_hal)
    target_include_directories(${drv} PRIVATE ${KR_DRIVER_DIR})
    # target_include_directories(${drv} PRIVATE ${OPENPLC_LIB_DIR})
    # target_compile_definitions(${drv} PRIVATE OPENPLC_V4_HEADERS=1)
    target_link_libraries(${drv} PRIVATE pthread)
    # Produce bare "fenet_hal.so" (no "lib" prefix) to match plugins.conf paths.
    set_target_properties(${drv} PROPERTIES PREFIX "")
    # Place built .so next to the other native plugins.
    set_target_properties(${drv} PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY
        ${CMAKE_BINARY_DIR}/core/src/drivers/plugins/native)
endforeach()
