//! The `math` module with Python's domain and range errors.

use crate::pyrt::raise;

fn domain() -> ! {
    raise("ValueError", "math domain error")
}

fn range_err() -> ! {
    raise("OverflowError", "math range error")
}

fn finite(x: f64, arg: f64) -> f64 {
    if x.is_infinite() && arg.is_finite() {
        range_err();
    }
    x
}

pub fn sqrt(x: f64) -> f64 {
    if x < 0.0 {
        domain();
    }
    x.sqrt()
}

pub fn log(x: f64) -> f64 {
    if x <= 0.0 {
        domain();
    }
    x.ln()
}

/// `math.log(x, base)`
pub fn log_base(x: f64, b: f64) -> f64 {
    if x <= 0.0 || b <= 0.0 {
        domain();
    }
    let d = b.ln();
    if d == 0.0 {
        raise("ZeroDivisionError", "float division by zero");
    }
    x.ln() / d
}

pub fn log2(x: f64) -> f64 {
    if x <= 0.0 {
        domain();
    }
    x.log2()
}

pub fn log10(x: f64) -> f64 {
    if x <= 0.0 {
        domain();
    }
    x.log10()
}

pub fn exp(x: f64) -> f64 {
    finite(x.exp(), x)
}

/// `math.fma(x, y, z)`: x * y + z with one rounding (a fused multiply-add).
pub fn fma(x: f64, y: f64, z: f64) -> f64 {
    x.mul_add(y, z)
}

/// `math.log1p(x)`: log(1 + x), accurate for small x.
pub fn log1p(x: f64) -> f64 {
    if x <= -1.0 {
        raise("ValueError", &format!("expected argument value > -1, got {}", crate::pyrt::float_repr(x)));
    }
    x.ln_1p()
}

/// `math.expm1(x)`: exp(x) - 1, accurate for small x.
pub fn expm1(x: f64) -> f64 {
    finite(x.exp_m1(), x)
}

pub fn asin(x: f64) -> f64 {
    if !(-1.0..=1.0).contains(&x) {
        domain();
    }
    x.asin()
}

pub fn acos(x: f64) -> f64 {
    if !(-1.0..=1.0).contains(&x) {
        domain();
    }
    x.acos()
}

pub fn sinh(x: f64) -> f64 {
    finite(x.sinh(), x)
}

pub fn cosh(x: f64) -> f64 {
    finite(x.cosh(), x)
}

pub fn pow(x: f64, y: f64) -> f64 {
    if x == 0.0 && y < 0.0 {
        domain();
    }
    if x < 0.0 && x.is_finite() && y.is_finite() && y.fract() != 0.0 {
        domain();
    }
    finite(x.powf(y), x + y)
}

pub fn fmod(x: f64, y: f64) -> f64 {
    if y == 0.0 || x.is_infinite() {
        domain();
    }
    x % y
}

fn to_int(x: f64) -> i64 {
    crate::pyrt::int_float(x)
}

pub fn floor(x: f64) -> i64 {
    to_int(x.floor())
}

pub fn ceil(x: f64) -> i64 {
    to_int(x.ceil())
}

pub fn trunc(x: f64) -> i64 {
    to_int(x.trunc())
}

pub fn gcd(a: i64, b: i64) -> i64 {
    let (mut a, mut b) = (a.unsigned_abs(), b.unsigned_abs());
    while b != 0 {
        (a, b) = (b, a % b);
    }
    i64::try_from(a).unwrap_or_else(|_| panic!("attempt to negate with overflow"))
}

pub fn lcm(a: i64, b: i64) -> i64 {
    if a == 0 || b == 0 {
        return 0;
    }
    (a / gcd(a, b) * b).abs()
}

pub fn isqrt(n: i64) -> i64 {
    if n < 0 {
        raise("ValueError", "isqrt() argument must be nonnegative");
    }
    let mut x = (n as f64).sqrt() as i64;
    while x * x > n {
        x -= 1;
    }
    while (x + 1) * (x + 1) <= n {
        x += 1;
    }
    x
}

pub fn factorial(n: i64) -> i64 {
    if n < 0 {
        raise("ValueError", "factorial() not defined for negative values");
    }
    (1..=n).product()
}

pub fn comb(n: i64, k: i64) -> i64 {
    if n < 0 || k < 0 {
        raise("ValueError", "n must be a non-negative integer");
    }
    if k > n {
        return 0;
    }
    let k = k.min(n - k);
    let mut r: i128 = 1;
    for i in 0..k {
        r = r * (n - i) as i128 / (i + 1) as i128;
        if r > i64::MAX as i128 {
            panic!("attempt to multiply with overflow");
        }
    }
    r as i64
}

pub fn perm(n: i64, k: i64) -> i64 {
    if n < 0 || k < 0 {
        raise("ValueError", "n must be a non-negative integer");
    }
    if k > n {
        return 0;
    }
    (n - k + 1..=n).product()
}

pub fn radians(x: f64) -> f64 {
    x * (std::f64::consts::PI / 180.0)
}

pub fn degrees(x: f64) -> f64 {
    x * (180.0 / std::f64::consts::PI)
}

/// `math.isclose(a, b)` with the default tolerances
pub fn isclose(a: f64, b: f64) -> bool {
    if a == b {
        return true;
    }
    if a.is_infinite() || b.is_infinite() {
        return false;
    }
    let d = (a - b).abs();
    d <= 1e-09 * b.abs() || d <= 1e-09 * a.abs()
}

fn float_arg(msg: &str, x: f64) -> ! {
    raise("ValueError", &format!("{}, got {}", msg, crate::pyrt::float_repr(x)))
}

// the platform's libm, as CPython uses it
mod libm {
    extern "C" {
        pub fn erf(x: f64) -> f64;
        pub fn erfc(x: f64) -> f64;
        pub fn asinh(x: f64) -> f64;
        pub fn acosh(x: f64) -> f64;
        pub fn atanh(x: f64) -> f64;
    }
}

pub fn erf(x: f64) -> f64 {
    unsafe { libm::erf(x) }
}

pub fn erfc(x: f64) -> f64 {
    unsafe { libm::erfc(x) }
}

pub fn asinh(x: f64) -> f64 {
    unsafe { libm::asinh(x) }
}

pub fn acosh(x: f64) -> f64 {
    if x < 1.0 {
        float_arg("expected argument value not less than 1", x);
    }
    unsafe { libm::acosh(x) }
}

pub fn atanh(x: f64) -> f64 {
    if x.abs() >= 1.0 {
        float_arg("expected a number between -1 and 1", x);
    }
    unsafe { libm::atanh(x) }
}

// gamma and lgamma: CPython's Lanczos approximation (Modules/mathmodule.c). The C
// compiler fuses its `a * b + c` into fused multiply-adds (clang on arm64 does), so
// these use `mul_add` there.

#[allow(clippy::excessive_precision)]
const LANCZOS_G: f64 = 6.024680040776729583740234375;
#[allow(clippy::excessive_precision)]
const LANCZOS_G_MINUS_HALF: f64 = 5.524680040776729583740234375;
#[allow(clippy::excessive_precision)]
const LANCZOS_NUM: [f64; 13] = [
    23531376880.410759688572007674451636754734846804940,
    42919803642.649098768957899047001988850926355848959,
    35711959237.355668049440185451547166705960488635843,
    17921034426.037209699919755754458931112671403265390,
    6039542586.3520280050642916443072979210699388420708,
    1439720407.3117216736632230727949123939715485786772,
    248874557.86205415651146038641322942321632125127801,
    31426415.585400194380614231628318205362874684987640,
    2876370.6289353724412254090516208496135991145378768,
    186056.26539522349504029498971604569928220784236328,
    8071.6720023658162106380029022722506138218516325024,
    210.82427775157934587250973392071336271166969580291,
    2.5066282746310002701649081771338373386264310793408,
];
const LANCZOS_DEN: [f64; 13] = [
    0.0, 39916800.0, 120543840.0, 150917976.0, 105258076.0, 45995730.0, 13339535.0, 2637558.0, 357423.0, 32670.0,
    1925.0, 66.0, 1.0,
];
const GAMMA_INTEGRAL: [f64; 23] = [
    1.0, 1.0, 2.0, 6.0, 24.0, 120.0, 720.0, 5040.0, 40320.0, 362880.0, 3628800.0, 39916800.0, 479001600.0,
    6227020800.0, 87178291200.0, 1307674368000.0, 20922789888000.0, 355687428096000.0, 6402373705728000.0,
    121645100408832000.0, 2432902008176640000.0, 51090942171709440000.0, 1124000727777607680000.0,
];
#[allow(clippy::excessive_precision)]
const LOGPI: f64 = 1.144729885849400174143427351353058711647;

fn lanczos_sum(x: f64) -> f64 {
    let (mut num, mut den) = (0.0f64, 0.0f64);
    if x < 5.0 {
        for (n, d) in LANCZOS_NUM.iter().zip(&LANCZOS_DEN).rev() {
            num = num.mul_add(x, *n);
            den = den.mul_add(x, *d);
        }
    } else {
        for (n, d) in LANCZOS_NUM.iter().zip(&LANCZOS_DEN) {
            num = num / x + n;
            den = den / x + d;
        }
    }
    num / den
}

/// sin(pi * x) for finite x
fn sinpi(x: f64) -> f64 {
    use std::f64::consts::PI;
    let y = x.abs() % 2.0;
    let r = match (2.0 * y).round() as i32 {
        0 => (PI * y).sin(),
        1 => (PI * (y - 0.5)).cos(),
        2 => (PI * (1.0 - y)).sin(),
        3 => -(PI * (y - 1.5)).cos(),
        _ => (PI * (y - 2.0)).sin(),
    };
    1.0f64.copysign(x) * r
}

const NONINT: &str = "expected a noninteger or positive integer";

pub fn gamma(x: f64) -> f64 {
    use std::f64::consts::PI;
    if !x.is_finite() {
        if x.is_nan() || x > 0.0 {
            return x;
        }
        float_arg(NONINT, x);
    }
    if x == x.floor() {
        if x <= 0.0 {
            float_arg(NONINT, x);
        }
        if x <= 23.0 {
            return GAMMA_INTEGRAL[x as usize - 1];
        }
    }
    let absx = x.abs();
    if absx < 1e-20 {
        return finite(1.0 / x, x);
    }
    if absx > 200.0 {
        if x < 0.0 {
            return 0.0 / sinpi(x);
        }
        range_err();
    }
    let y = absx + LANCZOS_G_MINUS_HALF;
    let mut z = if absx > LANCZOS_G_MINUS_HALF { (y - absx) - LANCZOS_G_MINUS_HALF } else { (y - LANCZOS_G_MINUS_HALF) - absx };
    z = z * LANCZOS_G / y;
    let mut r;
    if x < 0.0 {
        r = -PI / sinpi(absx) / absx * y.exp() / lanczos_sum(absx);
        r = (-z).mul_add(r, r);
        if absx < 140.0 {
            r /= y.powf(absx - 0.5);
        } else {
            let s = y.powf(absx / 2.0 - 0.25);
            r /= s;
            r /= s;
        }
    } else {
        r = lanczos_sum(absx) / y.exp();
        r = z.mul_add(r, r);
        if absx < 140.0 {
            r *= y.powf(absx - 0.5);
        } else {
            let s = y.powf(absx / 2.0 - 0.25);
            r *= s;
            r *= s;
        }
    }
    finite(r, x)
}

pub fn lgamma(x: f64) -> f64 {
    if !x.is_finite() {
        return if x.is_nan() { x } else { f64::INFINITY };
    }
    if x == x.floor() && x <= 2.0 {
        if x <= 0.0 {
            float_arg(NONINT, x);
        }
        return 0.0;
    }
    let absx = x.abs();
    if absx < 1e-20 {
        return -absx.ln();
    }
    let mut r = lanczos_sum(absx).ln() - LANCZOS_G;
    r = (absx - 0.5).mul_add((absx + LANCZOS_G - 0.5).ln() - 1.0, r);
    if x < 0.0 {
        r = LOGPI - sinpi(absx).abs().ln() - absx.ln() - r;
    }
    finite(r, x)
}

/// `math.fsum`: Shewchuk's exact partial sums, rounded as CPython rounds them.
pub fn fsum<I: IntoIterator<Item = f64>>(it: I) -> f64 {
    let mut p: Vec<f64> = vec![];
    let (mut special, mut inf_sum) = (0.0f64, 0.0f64);
    for x0 in it {
        let mut x = x0;
        let mut i = 0;
        #[allow(clippy::needless_range_loop)]
        for j in 0..p.len() {
            let mut y = p[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                p[i] = lo;
                i += 1;
            }
            x = hi;
        }
        p.truncate(i);
        if x != 0.0 {
            if !x.is_finite() {
                if x0.is_finite() {
                    raise("OverflowError", "intermediate overflow in fsum");
                }
                if x0.is_infinite() {
                    inf_sum += x0;
                }
                special += x0;
                p.clear();
            } else {
                p.push(x);
            }
        }
    }
    if special != 0.0 {
        if inf_sum.is_nan() {
            raise("ValueError", "-inf + inf in fsum");
        }
        return special;
    }
    let mut n = p.len();
    if n == 0 {
        return 0.0;
    }
    n -= 1;
    let mut hi = p[n];
    let mut lo = 0.0;
    while n > 0 {
        let x = hi;
        n -= 1;
        let y = p[n];
        hi = x + y;
        lo = y - (hi - x);
        if lo != 0.0 {
            break;
        }
    }
    if n > 0 && ((lo < 0.0 && p[n - 1] < 0.0) || (lo > 0.0 && p[n - 1] > 0.0)) {
        let y = lo * 2.0;
        let x = hi + y;
        if y == x - hi {
            hi = x;
        }
    }
    hi
}

/// `math.nextafter(x, y)`: the float after x towards y
pub fn nextafter(x: f64, y: f64) -> f64 {
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    if x == y {
        return y;
    }
    if x == 0.0 {
        return f64::from_bits(1).copysign(y);
    }
    let b = x.to_bits();
    // away from zero when y is further from zero on x's side
    f64::from_bits(if (y > x) == (x > 0.0) { b + 1 } else { b - 1 })
}

/// `math.ulp(x)`: the gap between |x| and the next float away from zero
pub fn ulp(x: f64) -> f64 {
    let x = x.abs();
    if x.is_nan() || x.is_infinite() {
        return x;
    }
    if x == f64::MAX {
        return x - nextafter(x, f64::NEG_INFINITY);
    }
    nextafter(x, f64::INFINITY) - x
}

/// `math.hypot(x, y)`: CPython's `vector_norm` (scaled, squared exactly with
/// fused multiply-adds, one differential correction), so the same bits
pub fn hypot(x: f64, y: f64) -> f64 {
    let (x, y) = (x.abs(), y.abs());
    let max = x.max(y);
    if max.is_infinite() {
        return max;
    }
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    if max == 0.0 {
        return max;
    }
    vector_norm(&[x, y], max)
}

fn vector_norm(v: &[f64], max: f64) -> f64 {
    let max_e = ((max.to_bits() >> 52) & 0x7ff) as i32 - 1022;
    if max.to_bits() >> 52 == 0 {
        // subnormal: scale up by DBL_MIN first
        let w: Vec<f64> = v.iter().map(|x| x / f64::MIN_POSITIVE).collect();
        return f64::MIN_POSITIVE * vector_norm(&w, max / f64::MIN_POSITIVE);
    }
    // 2 ** -max_e (subnormal for max_e > 1022)
    let k = -max_e;
    let scale = if k >= -1022 { f64::from_bits(((1023 + k) as u64) << 52) } else { f64::from_bits(1u64 << (k + 1074)) };
    // csum, frac1, frac2: the exact sum is csum + frac1 + frac2 (lossless, lossy, lossy)
    let mut s = (1.0f64, 0.0f64, 0.0f64);
    fn add(s: &mut (f64, f64, f64), hi: f64, lo: f64) {
        let t = s.0 + hi;
        let z = t - s.0;
        s.2 += hi - z;
        s.0 = t;
        s.1 += lo;
    }
    for &x in v {
        let x = x * scale;
        let p = x * x;
        add(&mut s, p, x.mul_add(x, -p));
    }
    let h = (s.0 - 1.0 + (s.1 + s.2)).sqrt();
    let p = -h * h;
    add(&mut s, p, (-h).mul_add(h, -p));
    let x = s.0 - 1.0 + (s.1 + s.2);
    (h + x / (2.0 * h)) / scale
}
