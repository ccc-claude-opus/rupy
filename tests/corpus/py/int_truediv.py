"""int / int is the exact quotient rounded once, also beyond 2**53."""

big = 2**62 + 1
print(9007199254740993 / 3, 9007199254740993 / 1, -9007199254740993 / 2)
print(big / 3, big / (2**61 + 3), 3 / big, -big / 7, big / -big)
print(0 / -(2**60), 1 / 9007199254740995, 9223372036854775807 / 9223372036854775806)
x = 1
for i in range(39):
    x = x * 3 + 1
    print(x / 7, x / 1000003, (x // 2 + 1) / x)
n = 7
try:
    print(n / (n - 7))
except ZeroDivisionError as e:
    print("ZeroDivisionError", e)
