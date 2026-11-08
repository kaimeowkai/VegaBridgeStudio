// Generate com.amazon.apmf bindings first; add the generated include directory
// and link the external SDK's apmf library. See docs/NATIVE-DEBUGGING.md.
#include <apmf/string.h>
#include <cstdio>

int main() {
    apmf::String text("WINDOWS_VEGA_API_OK");
    std::printf("%s %zu\n", text.c_str(), text.size());
    return text.size() == 19 ? 0 : 1;
}
