#import <CFNetwork/CFNetwork.h>
#import <Foundation/Foundation.h>

#include <stdio.h>
#include <stdlib.h>

/*
 * Makes BestHTTP use the iOS manual HTTP proxy instead of connecting
 * directly. Runs as a constructor when the dylib is injected, before the
 * app starts. BestHTTP reads http_proxy/https_proxy (lowercase then
 * uppercase); both variants are exported.
 *
 * Optional override: <Documents>/proxy_override.txt containing "host:port"
 * wins over the system settings.
 */

static FILE *gLog;

static void L(const char *msg) {
    if (!gLog) {
        NSString *path = [NSHomeDirectory()
            stringByAppendingPathComponent:@"Documents/proxy_redirect.log"];
        gLog = fopen(path.fileSystemRepresentation, "a");
        if (gLog) {
            setvbuf(gLog, NULL, _IONBF, 0);
        }
    }
    fprintf(gLog ? gLog : stderr, "[ProxyRedirect] %s\n", msg);
}

static BOOL IsEnabled(NSDictionary *settings, NSString *key) {
    id value = settings[key];
    return [value respondsToSelector:@selector(boolValue)] &&
           [value boolValue];
}

static NSString *CopySystemProxyURL(void) {
    CFDictionaryRef copiedSettings = CFNetworkCopySystemProxySettings();
    if (copiedSettings == NULL) {
        return nil;
    }

    NSDictionary *settings = CFBridgingRelease(copiedSettings);
    NSString *enableKey = (__bridge NSString *)kCFNetworkProxiesHTTPEnable;
    NSString *hostKey = (__bridge NSString *)kCFNetworkProxiesHTTPProxy;
    NSString *portKey = (__bridge NSString *)kCFNetworkProxiesHTTPPort;

    if (!IsEnabled(settings, enableKey)) {
        return nil;
    }

    id hostValue = settings[hostKey];
    id portValue = settings[portKey];
    if (![hostValue isKindOfClass:NSString.class] ||
        ![portValue respondsToSelector:@selector(integerValue)]) {
        return nil;
    }

    NSString *host = [(NSString *)hostValue
        stringByTrimmingCharactersInSet:
            NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSInteger port = [portValue integerValue];
    if (host.length == 0 || port <= 0 || port > UINT16_MAX) {
        return nil;
    }

    if ([host containsString:@":"] && ![host hasPrefix:@"["]) {
        host = [NSString stringWithFormat:@"[%@]", host];
    }

    return [NSString stringWithFormat:@"http://%@:%ld", host, (long)port];
}

static NSString *CopyOverrideProxyURL(void) {
    NSString *path = [NSHomeDirectory()
        stringByAppendingPathComponent:@"Documents/proxy_override.txt"];
    NSString *raw = [NSString stringWithContentsOfFile:path
                                              encoding:NSUTF8StringEncoding
                                                 error:nil];
    if (!raw) {
        return nil;
    }
    raw = [raw stringByTrimmingCharactersInSet:
        NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (raw.length == 0) {
        return nil;
    }

    NSArray<NSString *> *parts = [raw componentsSeparatedByString:@":"];
    NSString *host;
    NSString *portPart;
    if (parts.count == 2) {
        host = parts[0];
        portPart = parts[1];
    } else if (parts.count > 2) {
        host = parts[0];
        for (NSUInteger i = 1; i < parts.count - 1; i++) {
            host = [host stringByAppendingFormat:@":%@", parts[i]];
        }
        portPart = parts[parts.count - 1];
    } else {
        return nil;
    }
    NSInteger port = portPart.integerValue;
    host = [host stringByTrimmingCharactersInSet:
        NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (host.length == 0 || port <= 0 || port > UINT16_MAX) {
        return nil;
    }
    if ([host containsString:@":"] && ![host hasPrefix:@"["]) {
        host = [NSString stringWithFormat:@"[%@]", host];
    }
    return [NSString stringWithFormat:@"http://%@:%ld", host, (long)port];
}

static void ExportProxyEnvironment(NSString *proxyURL) {
    const char *value = proxyURL.UTF8String;
    if (value == NULL || value[0] == '\0') {
        return;
    }

    setenv("http_proxy", value, 1);
    setenv("https_proxy", value, 1);
    setenv("HTTP_PROXY", value, 1);
    setenv("HTTPS_PROXY", value, 1);
    L([NSString stringWithFormat:@"proxy -> %@", proxyURL].UTF8String);
}

__attribute__((constructor))
static void InitializeProxyEnvironment(void) {
    @autoreleasepool {
        NSString *proxy = CopyOverrideProxyURL();
        if (proxy) {
            L("using override file");
            ExportProxyEnvironment(proxy);
            return;
        }
        proxy = CopySystemProxyURL();
        if (proxy) {
            L("using system proxy");
            ExportProxyEnvironment(proxy);
            return;
        }
        L("no proxy configured; leaving app connections unchanged");
    }
}
