import statistics
from statistics import NormalDist, StatisticsError

data = [2.75, 1.75, 1.25, 0.25, 0.5, 1.25, 3.5]
print(statistics.mean(data), statistics.fmean(data), statistics.median(data))
print(statistics.variance(data), statistics.pvariance(data), statistics.stdev(data), statistics.pstdev(data))
print(statistics.median_low([1, 3, 5, 7]), statistics.median_high([1, 3, 5, 7]), statistics.median([1.0, 3.0, 5.0, 7.0]))
print(statistics.median_grouped([52, 52, 53, 54]), statistics.median_grouped([1, 3, 3, 5, 7], interval=2))
print(statistics.mode([1, 1, 2, 3, 3, 3, 3, 4]), statistics.mode(["red", "blue", "blue", "red", "green", "red"]))
print(statistics.multimode(list("aabbbbccddddeeffffgg")), statistics.multimode([0.5, 1.5]))
print(statistics.harmonic_mean([40.0, 60.0]), statistics.harmonic_mean([40.0, 60.0], weights=[5.0, 30.0]))
print(statistics.fmean([3.5, 4.0, 5.25], weights=[0.25, 0.5, 0.25]), statistics.fmean([1, 2, 3, 4]))
print(statistics.quantiles([105.0, 129.0, 87.0, 86.0, 111.0, 111.0, 89.0, 81.0, 108.0, 92.0, 110.0, 100.0, 75.0, 105.0, 103.0, 109.0, 76.0, 119.0, 99.0, 91.0, 103.0, 129.0, 106.0, 101.0, 84.0, 111.0, 74.0, 87.0, 86.0, 103.0, 103.0, 106.0, 86.0, 111.0, 75.0, 87.0, 102.0, 121.0, 111.0, 88.0, 89.0, 101.0, 106.0, 95.0, 103.0, 107.0, 101.0, 81.0, 109.0, 104.0], n=10))
print(statistics.quantiles([1.0, 2.0, 3.0, 4.0, 5.0], method="inclusive"), statistics.quantiles([7.5], n=3))
x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
y = [1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 1.0, 2.0, 3.0]
z = list(reversed(x))
print(statistics.covariance(x, y), statistics.covariance(z, x))
print(statistics.correlation(x, x), statistics.correlation(x, z), statistics.correlation(x, y))
print(statistics.correlation([1.0, 2.0, 2.0, 4.0, 9.0], [3.0, 3.5, 1.0, 8.0, 7.0], method="ranked"))
lr = statistics.linear_regression([1971.0, 1975.0, 1979.0, 1982.0, 1983.0], [1.0, 2.0, 3.0, 4.0, 5.0])
print(lr, lr.slope, lr.intercept)
print(statistics.linear_regression([1.0, 2.0, 3.0], [2.0, 4.1, 5.9], proportional=True))
print(statistics.stdev([1, 2, 3, 4, 5, 6]), statistics.pstdev([10, 20]))
print(statistics.variance(data, 1.0), statistics.pvariance(data, mu=1.5), statistics.stdev(data, 1.0))

# exact sums: what a naive float sum gets wrong
print(statistics.mean([1e20, 1.0, -1e20, 3.0]), statistics.variance([1e8 + 0.1, 1e8 + 0.2, 1e8 + 0.3]))
print(statistics.mean([0.1] * 10), statistics.stdev([0.1, 0.2, 0.3, 0.4]), statistics.pvariance([1e-3, 2e-3, 4e-3]))
vals = [float(i * i % 97) / 7.0 + 0.1 for i in range(200)]
print(statistics.mean(vals), statistics.variance(vals), statistics.stdev(vals), statistics.pstdev(vals))
print(statistics.harmonic_mean(vals[1:]), statistics.median(vals), statistics.mean([float("inf"), 1.0]), statistics.variance([1.0, float("inf")]))

nd = NormalDist(100, 15)
print(nd, nd.mean, nd.stdev, nd.variance, nd.median, nd.mode)
print(nd.cdf(130.0), nd.inv_cdf(0.975), nd.inv_cdf(0.5), nd.inv_cdf(0.001), nd.inv_cdf(1e-300), nd.zscore(70.0))
print(nd.quantiles(), [round(q, 9) for q in nd.quantiles(10)])
print(nd + 5.0, 5.0 + nd, nd - 5.0, 100.0 - nd, nd * 2.0, 2.0 * nd, nd / 3.0, -nd, +nd)
print(nd + NormalDist(1, 2), nd - NormalDist(1, 2), nd == NormalDist(100, 15), nd == NormalDist())
print(NormalDist.from_samples([2.5, 3.25, 5.5, 11.25, 11.75]))
print(round(NormalDist(2.4, 1.6).overlap(NormalDist(3.2, 2.0)), 12), NormalDist(1, 2).overlap(NormalDist(3, 2)))
print(round(nd.pdf(110.0), 15))

for k in range(8):
    try:
        if k == 0:
            statistics.mean([])
        elif k == 1:
            statistics.variance([1.0])
        elif k == 2:
            empty: list[str] = []
            statistics.mode(empty)
        elif k == 3:
            statistics.harmonic_mean([1.0, -2.0])
        elif k == 4:
            statistics.correlation([1.0, 1.0], [1.0, 2.0])
        elif k == 5:
            NormalDist(0, -1)
        elif k == 6:
            statistics.stdev([1.0, float("nan")])
        else:
            statistics.quantiles([1.0, 2.0], method="other")
    except StatisticsError as e:
        print("StatisticsError", e)
    except ValueError as e:
        print("ValueError", e)
