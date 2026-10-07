find_package(PkgConfig)

PKG_CHECK_MODULES(PC_GR_OPEN_MODEM gnuradio-open_modem)

FIND_PATH(
    GR_OPEN_MODEM_INCLUDE_DIRS
    NAMES gnuradio/open_modem/api.h
    HINTS $ENV{OPEN_MODEM_DIR}/include
        ${PC_OPEN_MODEM_INCLUDEDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/include
          /usr/local/include
          /usr/include
)

FIND_LIBRARY(
    GR_OPEN_MODEM_LIBRARIES
    NAMES gnuradio-open_modem
    HINTS $ENV{OPEN_MODEM_DIR}/lib
        ${PC_OPEN_MODEM_LIBDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/lib
          ${CMAKE_INSTALL_PREFIX}/lib64
          /usr/local/lib
          /usr/local/lib64
          /usr/lib
          /usr/lib64
          )

include("${CMAKE_CURRENT_LIST_DIR}/gnuradio-open_modemTarget.cmake")

INCLUDE(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(GR_OPEN_MODEM DEFAULT_MSG GR_OPEN_MODEM_LIBRARIES GR_OPEN_MODEM_INCLUDE_DIRS)
MARK_AS_ADVANCED(GR_OPEN_MODEM_LIBRARIES GR_OPEN_MODEM_INCLUDE_DIRS)
