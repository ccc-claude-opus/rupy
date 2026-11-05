"""rstat: R's hypothesis tests and descriptive statistics, printed as R prints them."""
import rstat as r

x = [5.1, 4.9, 6.2, 5.8, 6.0, 5.5, 5.3, 6.1]
y = [4.8, 5.2, 5.0, 5.6, 4.7, 5.1, 4.9, 5.3]
print(r.t_test(x, mu=5.0))
print(r.t_test(x, y))
print(r.t_test(x, y, var_equal=True))
print(r.t_test(x, y, paired=True))
print(r.t_test(x, mu=5.5, alternative="less"))
print(r.var_test(x, y))
print(r.chisq_test([20.0, 30.0, 25.0, 25.0], data_name="c(20, 30, 25, 25)"))
print(r.chisq_test_table([[12.0, 5.0], [7.0, 9.0]], data_name="matrix(c(12, 5, 7, 9), 2, byrow = TRUE)"))
print(r.binom_test(7, 20))
print(r.prop_test(15, 40))
print(r.cor_test(x, y))
print(r.summary(x))
print(r.quantile(x))
print(r.quantile(x, [0.1, 0.33, 0.9], type=6))
print(r.print_vector(r.fivenum(x)))
print(r.print_vector([r.mad(x)]))
print(r.print_vector([r.IQR(x)]))
print(r.print_vector([r.median(y)]))
print(r.print_vector([r.sd(x)]))
print(r.print_vector([r.var(y)]))
print(r.print_vector([r.cor(x, y, method="spearman")]))
print(r.print_vector([r.cor(x, y, method="kendall")]))
