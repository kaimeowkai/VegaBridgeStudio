#include <stdio.h>

int calculate(int seed) {
    int answer = seed + 5;
    answer *= 2; /* Set a breakpoint here: answer is 12 before stepping. */
    return answer; /* After Step over: answer is 24. */
}

int main(void) {
    int value = calculate(7);
    printf("answer=%d\n", value);
    return value == 24 ? 0 : 1;
}
