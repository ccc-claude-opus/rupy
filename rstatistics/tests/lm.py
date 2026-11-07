import rstatistics as r

x = [5.1, 4.9, 6.2, 5.8, 6.0, 5.5, 5.3, 6.1]
z = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
w = [2.0, 3.0, 1.0, 5.0, 4.0, 8.0, 7.0, 6.0]
y = [1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2]
g = ["a", "a", "b", "b", "c", "c", "d", "d"]
m = r.lm(y, [x], ["x"])
print(m.summary())
print(r.Named(["(Intercept)", "x"], m.coefficients))
print(r.Named([str(i + 1) for i in range(len(y))], m.fitted_values))
print(r.Named([str(i + 1) for i in range(len(y))], m.residuals))
print(r.print_vector([m.df_residual]))
m2 = r.lm(y, [x, z], ["x", "z"])
print(m2.summary())
print(r.anova(m2))
print(r.anova(r.lm(y, [x, z, w], ["x", "z", "w"])))
a = r.aov(y, g)
print(a)
print(a.summary())
nx = [[6.0, 6.5, 5.0]]
print(r.predict(m, nx))
print(r.predict(m, nx, "confidence"))
print(r.predict(m, nx, "prediction"))
