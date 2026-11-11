cmake_minimum_required(VERSION 3.10)
project(qmgc CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PNG REQUIRED)
find_package(JPEG)

add_library(qmgc_lib
    src/residual.cpp
    src/image.cpp
    src/encode_w2.cpp
    src/encode_a9ll.cpp
    src/encode.cpp
)
target_include_directories(qmgc_lib PUBLIC include)
target_include_directories(qmgc_lib PRIVATE src)
target_link_libraries(qmgc_lib PUBLIC PNG::PNG)
if(JPEG_FOUND)
    target_compile_definitions(qmgc_lib PUBLIC QMGC_HAVE_JPEG)
    target_link_libraries(qmgc_lib PUBLIC JPEG::JPEG)
endif()

add_executable(qmgc tools/qmgc.cpp)
target_include_directories(qmgc PRIVATE src)
target_link_libraries(qmgc PRIVATE qmgc_lib pthread)

install(TARGETS qmgc RUNTIME DESTINATION bin)
