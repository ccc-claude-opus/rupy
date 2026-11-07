"""rstatistics: the linear models of R's stats package (lm, anova, aov, predict)."""
import rstatistics as r

x = [5.1, 4.9, 6.2, 5.8, 6.0, 5.5, 5.3, 6.1]
z = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
y = [1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2]
g = ["a", "a", "b", "b", "c", "c", "d", "d"]
m = r.lm(y, [x], ["x"])
print(r.format_num(m.coefficients[0]))
print(r.format_num(m.coefficients[1]))
print(r.format_num(m.fitted_values[0]))
print(r.format_num(m.residuals[0]))
print(r.format_num(m.df_residual))
s = m.summary()
print(r.format_num(s.p_values[0]))
print(r.format_num(s.r_squared))
print(r.format_num(s.adj_r_squared))
print(r.format_num(s.f_statistic[0]))
m2 = r.lm(y, [x, z], ["x", "z"])
print(r.format_num(m2.coefficients[0]))
print(r.format_num(m2.coefficients[1]))
print(r.format_num(m2.coefficients[2]))
print(r.anova(m2))
a = r.aov(y, g)
print(a)
print(r.predict(m, [[6.0, 6.5, 5.0]], "confidence"))
