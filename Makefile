# Builds out/ProxyRedirect.dylib (constructor-only, no Python needed).

ROOT := $(abspath .)
OUT := out
SDK ?= $(shell xcrun --sdk iphoneos --show-sdk-path)
MIN_IOS ?= 13.0
ARCH ?= arm64
CC ?= $(shell xcrun --sdk iphoneos -f clang)

CFLAGS := -arch $(ARCH) -isysroot $(SDK) -miphoneos-version-min=$(MIN_IOS) \
	-fobjc-arc -fPIC -O2 -Wall -Werror
LDFLAGS := -arch $(ARCH) -isysroot $(SDK) -miphoneos-version-min=$(MIN_IOS) \
	-framework Foundation -framework CFNetwork

.PHONY: all clean

all: check-sdk $(OUT)/ProxyRedirect.dylib

check-sdk:
	@test -d "$(SDK)" || (echo "missing iOS SDK; install Xcode Command Line Tools" >&2; exit 1)

$(OUT):
	mkdir -p $(OUT)

$(OUT)/ProxyRedirect.o: src/ProxyRedirect.m | $(OUT)
	$(CC) $(CFLAGS) -c -o $@ src/ProxyRedirect.m

$(OUT)/ProxyRedirect.dylib: $(OUT)/ProxyRedirect.o
	$(CC) $(LDFLAGS) -dynamiclib \
		-install_name @executable_path/ProxyRedirect.dylib \
		-o $@ $^
	codesign --force --sign - --timestamp=none $@
	@echo "built $@"

clean:
	rm -rf $(OUT)
