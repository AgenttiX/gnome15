#!/bin/sh

BUILD_LOG="build-log.txt"

autoreconf -i 2>&1 | tee ${BUILD_LOG}
./configure | tee -a ${BUILD_LOG}
make | ${BUILD_LOG}
sudo make uninstall | tee -a ${BUILD_LOG}
sudo make install | tee -a ${BUILD_LOG}
