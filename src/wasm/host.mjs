// The host of rupy programs compiled to WebAssembly (`rupy wasm`).
//
// In a browser:  import { run } from "./rupy_wasm.mjs";
//                const code = await run(bytes, { stdout: s => ..., stderr: s => ..., stdin: "..." });
// On the command line (Node.js 22+):  node rupy_wasm.mjs prog.wasm < input
//
// The module calls the host through a small channel: arguments are pushed one
// by one (strings through the exported memory), `call` / `fcall` run a named
// operation, and strings come back through `pending` + `take`. The operations
// follow CPython: float repr and format specs (exact decimal rounding), int()
// and float() parsing, math with its domain errors, str methods.

const KINDS = [
  "", "ValueError", "TypeError", "OverflowError", "IndexError", "EOFError", "ZeroDivisionError", "KeyError",
  // from packages (rupy_lib.wasm)
  "RuntimeError", "NotImplementedError", "AttributeError", "OSError", "FileNotFoundError", "AssertionError",
  "LookupError", "ArithmeticError", "Exception",
];
const enc = new TextEncoder();
const dec = new TextDecoder();

class PyErr {
  constructor(kind, msg) {
    this.kind = kind;
    this.msg = msg;
  }
}
const err = (kind, msg) => new PyErr(kind, msg);

// ------------------------------------------------------------ numbers

const I64_MIN = -(2n ** 63n), I64_MAX = 2n ** 63n - 1n;
const OVERFLOW = "integer overflow (py2rs: int is a 64-bit integer)";

/** repr(float) */
function floatRepr(x) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const [m, e] = Math.abs(x).toExponential().split("e");
  const exp = parseInt(e, 10);
  const digits = m.replace(".", "");
  const sign = x < 0 ? "-" : "";
  if (exp < -4 || exp >= 16) {
    const mm = digits.length > 1 ? digits[0] + "." + digits.slice(1) : digits;
    return sign + mm + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
  }
  let s;
  if (exp >= 0) {
    s = digits.length <= exp + 1 ? digits + "0".repeat(exp + 1 - digits.length) + ".0" : digits.slice(0, exp + 1) + "." + digits.slice(exp + 1);
  } else {
    s = "0." + "0".repeat(-exp - 1) + digits;
  }
  return sign + s;
}

/** x (finite, > 0) = D * 10^k exactly */
function decompose(x) {
  const v = new DataView(new ArrayBuffer(8));
  v.setFloat64(0, x);
  const bits = v.getBigUint64(0);
  const ex = Number((bits >> 52n) & 0x7ffn);
  const frac = bits & ((1n << 52n) - 1n);
  const m = ex === 0 ? frac : frac | (1n << 52n);
  const e = ex === 0 ? -1074 : ex - 1075;
  return e >= 0 ? [m << BigInt(e), 0] : [m * 5n ** BigInt(-e), e];
}

/** n / d rounded half to even (n ≥ 0, d > 0) */
function roundDiv(n, d) {
  let q = n / d;
  const r2 = (n % d) * 2n;
  if (r2 > d || (r2 === d && q % 2n === 1n)) q += 1n;
  return q;
}

/** |x| with `prec` decimals, correctly rounded: [integer digits, fraction digits] */
function fixed(x, prec) {
  if (x === 0) return ["0", "0".repeat(prec)];
  const [D, k] = decompose(Math.abs(x));
  const scale = k + prec;
  const N = scale >= 0 ? D * 10n ** BigInt(scale) : roundDiv(D, 10n ** BigInt(-scale));
  const s = N.toString().padStart(prec + 1, "0");
  return [s.slice(0, s.length - prec), s.slice(s.length - prec)];
}

/** |x| to `prec` + 1 significant digits: [digits, decimal exponent] */
function sci(x, prec) {
  if (x === 0) return ["0".repeat(prec + 1), 0];
  const [D, k] = decompose(Math.abs(x));
  let exp = D.toString().length - 1 + k;
  const scale = k - exp + prec;
  let N = scale >= 0 ? D * 10n ** BigInt(scale) : roundDiv(D, 10n ** BigInt(-scale));
  if (N.toString().length > prec + 1) {
    N /= 10n;
    exp += 1;
  }
  return [N.toString(), exp];
}

/** round(x, n) as Python: the decimal value nearest to x, half to even */
function roundTo(x, n) {
  if (!Number.isFinite(x) || x === 0) return x;
  if (n >= 0) {
    if (n > 330) return x;
    const [i, f] = fixed(x, n);
    const r = parseFloat(i + "." + (f || "0"));
    return x < 0 ? -r : r;
  }
  const [D, k] = decompose(Math.abs(x));
  const scale = k + n;
  const N = scale >= 0 ? D * 10n ** BigInt(scale) : roundDiv(D, 10n ** BigInt(-scale));
  const r = parseFloat(N.toString() + "e" + -n);
  return x < 0 ? -r : r;
}

function group(intPart, sep, every) {
  if (!sep) return intPart;
  let out = "";
  for (let i = 0; i < intPart.length; i++) {
    if (i > 0 && (intPart.length - i) % every === 0) out += sep;
    out += intPart[i];
  }
  return out;
}

const SPEC = /^(?:(.)?([<>=^]))?([-+ ])?(z)?(#)?(0)?(\d+)?([,_])?(?:\.(\d+))?([a-zA-Z%])?$/su;

function pad(body, sign, prefix, f, numeric) {
  const width = f.width;
  let fill = f.fill, align = f.align;
  if (f.zero && !align) {
    fill = fill ?? "0";
    align = "=";
  }
  fill = fill ?? " ";
  align = align ?? (numeric ? ">" : "<");
  const len = [...(sign + prefix + body)].length;
  if (width <= len) return sign + prefix + body;
  const n = width - len;
  switch (align) {
    case "<":
      return sign + prefix + body + fill.repeat(n);
    case ">":
      return fill.repeat(n) + sign + prefix + body;
    case "^":
      return fill.repeat(n >> 1) + sign + prefix + body + fill.repeat(n - (n >> 1));
    default:
      return sign + prefix + fill.repeat(n) + body;
  }
}

function parseSpec(spec, typeName) {
  const m = SPEC.exec(spec);
  if (!m) throw err("ValueError", "Invalid format specifier '" + spec + "' for object of type '" + typeName + "'");
  return { fill: m[1], align: m[2], sign: m[3] ?? "-", signed: m[3] !== undefined, z: !!m[4], alt: !!m[5], zero: !!m[6], width: m[7] ? parseInt(m[7], 10) : 0, group: m[8], prec: m[9] !== undefined ? parseInt(m[9], 10) : null, type: m[10] ?? "" };
}

const signOf = (neg, f) => (neg ? "-" : f.sign === "+" ? "+" : f.sign === " " ? " " : "");

function formatFloat(x, f, typeName = "float") {
  let t = f.type;
  if (!"eEfFgGn%".includes(t) && t !== "") throw err("ValueError", "Unknown format code '" + t + "' for object of type '" + typeName + "'");
  let neg = x < 0 || Object.is(x, -0);
  let body;
  const upper = "EFG".includes(t);
  if (Number.isNaN(x)) {
    neg = false;
    body = upper ? "NAN" : "nan";
  } else if (!Number.isFinite(x)) {
    body = upper ? "INF" : "inf";
  } else {
    const ax = Math.abs(x);
    let prec = f.prec;
    if (t === "") {
      if (prec === null) {
        body = floatRepr(ax);
      } else {
        body = general(ax, prec, f.alt);
        if (!body.includes(".") && !body.includes("e")) body += ".0";
      }
    } else if (t === "f" || t === "F" || t === "%") {
      const v = t === "%" ? ax * 100 : ax;
      const [i, fr] = fixed(v, prec ?? 6);
      body = group(i, f.group, 3) + (fr || f.alt ? "." + fr : "") + (t === "%" ? "%" : "");
      if (f.z && /^[0.]*%?$/.test(i + fr)) neg = false;
    } else if (t === "e" || t === "E") {
      const p = prec ?? 6;
      const [d, e] = sci(ax, p);
      body = d[0] + (p > 0 || f.alt ? "." + d.slice(1) : "") + (t === "E" ? "E" : "e") + (e < 0 ? "-" : "+") + String(Math.abs(e)).padStart(2, "0");
    } else {
      body = general(ax, prec ?? 6, f.alt);
      if (t === "G") body = body.toUpperCase();
    }
    if (f.group && t !== "f" && t !== "F" && t !== "%") {
      const m = /^(\d+)(.*)$/s.exec(body);
      if (m) body = group(m[1], f.group, 3) + m[2];
    }
    if (f.z && Number(body.replace(/[^\d.e+-]/g, "")) === 0) neg = false;
  }
  return pad(body, signOf(neg, f), "", f, true);
}

/** 'g' formatting of |x| with precision p */
function general(ax, p, alt) {
  if (p === 0) p = 1;
  const [d, e] = sci(ax, p - 1);
  let s;
  if (e >= -4 && e < p) {
    const [i, fr] = fixed(ax, p - 1 - e);
    s = i + (fr ? "." + fr : "");
    if (!alt && s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
    if (alt && !s.includes(".")) s += ".";
  } else {
    let m = d[0] + (d.length > 1 ? "." + d.slice(1) : "");
    if (!alt && m.includes(".")) m = m.replace(/0+$/, "").replace(/\.$/, "");
    if (alt && !m.includes(".")) m += ".";
    s = m + "e" + (e < 0 ? "-" : "+") + String(Math.abs(e)).padStart(2, "0");
  }
  return s;
}

function formatInt(x, f) {
  const t = f.type;
  if ("eEfFgG%".includes(t) && t) return formatFloat(Number(x), f, "int");
  if (!"bcdoxXn".includes(t) && t !== "") throw err("ValueError", "Unknown format code '" + t + "' for object of type 'int'");
  if (f.prec !== null) throw err("ValueError", "Precision not allowed in integer format specifier");
  if (t === "c") return pad(String.fromCodePoint(Number(x)), "", "", f, true);
  const neg = x < 0n;
  const ax = neg ? -x : x;
  const base = { b: 2, o: 8, x: 16, X: 16 }[t] ?? 10;
  let body = ax.toString(base);
  if (t === "X") body = body.toUpperCase();
  body = group(body, f.group, base === 10 ? 3 : 4);
  const prefix = f.alt && base !== 10 ? "0" + (t === "X" ? "X" : t) : "";
  return pad(body, signOf(neg, f), prefix, f, true);
}

function formatStr(s, f) {
  if (f.type !== "" && f.type !== "s") throw err("ValueError", "Unknown format code '" + f.type + "' for object of type 'str'");
  if (f.align === "=") throw err("ValueError", "'=' alignment not allowed in string format specifier");
  if (f.signed) throw err("ValueError", "Sign not allowed in string format specifier");
  let body = s;
  if (f.prec !== null) body = [...body].slice(0, f.prec).join("");
  return pad(body, "", "", f, false);
}

function format(v, spec) {
  if (spec === "") return typeof v === "number" ? floatRepr(v) : String(v);
  if (typeof v === "bigint") return formatInt(v, parseSpec(spec, "int"));
  if (typeof v === "number") return formatFloat(v, parseSpec(spec, "float"));
  return formatStr(v, parseSpec(spec, "str"));
}

const pyRepr = (s) => {
  const q = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = q;
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (ch === "\\" || ch === q) out += "\\" + ch;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    // what str.isprintable() rejects: control, format, private, unassigned, separators but ' '
    else if (ch !== " " && /[\p{C}\p{Z}]/u.test(ch)) {
      if (c < 0x100) out += "\\x" + c.toString(16).padStart(2, "0");
      else if (c < 0x10000) out += "\\u" + c.toString(16).padStart(4, "0");
      else out += "\\U" + c.toString(16).padStart(8, "0");
    } else out += ch;
  }
  return out + q;
};

function parseInt64(s, base) {
  const orig = s;
  const bad = () => err("ValueError", "invalid literal for int() with base " + base + ": " + pyRepr(orig));
  s = s.replace(/^[\s]+|[\s]+$/gu, "");
  let neg = false;
  if (s[0] === "+" || s[0] === "-") {
    neg = s[0] === "-";
    s = s.slice(1);
  }
  let b = base;
  const pre = s.slice(0, 2).toLowerCase();
  if ((b === 16 && pre === "0x") || (b === 8 && pre === "0o") || (b === 2 && pre === "0b")) s = s.slice(2).replace(/^_/, "");
  else if (b === 0) {
    if (pre === "0x") (b = 16), (s = s.slice(2).replace(/^_/, ""));
    else if (pre === "0o") (b = 8), (s = s.slice(2).replace(/^_/, ""));
    else if (pre === "0b") (b = 2), (s = s.slice(2).replace(/^_/, ""));
    else {
      b = 10;
      if (/^0+[1-9]/.test(s)) throw bad();
    }
  }
  if (!s || s.startsWith("_") || s.endsWith("_") || s.includes("__")) throw bad();
  s = s.replace(/_/g, "");
  let v = 0n;
  const B = BigInt(b);
  for (const ch of s) {
    let d;
    const c = ch.codePointAt(0);
    if (c >= 48 && c <= 57) d = c - 48;
    else if (c >= 97 && c <= 122) d = c - 87;
    else if (c >= 65 && c <= 90) d = c - 55;
    else {
      // other Unicode decimal digits
      const n = /\p{Nd}/u.test(ch) ? Number.parseInt(ch.normalize("NFKD"), 10) : NaN;
      if (Number.isNaN(n)) throw bad();
      d = n;
    }
    if (d >= b) throw bad();
    v = v * B + BigInt(d);
  }
  if (neg) v = -v;
  if (v < I64_MIN || v > I64_MAX) throw err("OverflowError", OVERFLOW);
  return v;
}

function parseFloat64(s) {
  const t = s.trim().replace(/(\d)_(?=\d)/g, "$1");
  const l = t.toLowerCase();
  const m = /^([+-]?)(inf|infinity|nan)$/.exec(l);
  if (m) return m[2] === "nan" ? NaN : m[1] === "-" ? -Infinity : Infinity;
  if (!/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(t)) throw err("ValueError", "could not convert string to float: " + pyRepr(s));
  return Number(t);
}

// ------------------------------------------------------------ math

const domain = () => err("ValueError", "math domain error");
const range = () => err("OverflowError", "math range error");

function checked(r, ...xs) {
  if (Number.isNaN(r) && !xs.some(Number.isNaN)) throw domain();
  if (!Number.isFinite(r) && !Number.isNaN(r) && xs.every(Number.isFinite)) throw range();
  return r;
}

const MATH = {
  pow: (a, b) => (a === 1 || b === 0 ? 1 : Math.pow(a, b)),
  fmod: (a, b) => a % b,
  round: (x, n) => roundTo(x, n),
  sin: (x) => checked(Math.sin(x), x),
  cos: (x) => checked(Math.cos(x), x),
  tan: (x) => checked(Math.tan(x), x),
  asin: (x) => checked(Math.asin(x), x),
  acos: (x) => checked(Math.acos(x), x),
  atan: (x) => Math.atan(x),
  atan2: (y, x) => Math.atan2(y, x),
  sinh: (x) => checked(Math.sinh(x), x),
  cosh: (x) => checked(Math.cosh(x), x),
  tanh: (x) => Math.tanh(x),
  exp: (x) => checked(Math.exp(x), x),
  expm1: (x) => checked(Math.expm1(x), x),
  log: (x) => {
    if (x <= 0) throw domain();
    return Math.log(x);
  },
  log2: (x) => {
    if (x <= 0) throw domain();
    return Math.log2(x);
  },
  log10: (x) => {
    if (x <= 0) throw domain();
    return Math.log10(x);
  },
  log1p: (x) => {
    if (x <= -1) throw err("ValueError", "expected argument value > -1, got " + floatRepr(x));
    return Math.log1p(x);
  },
  log_base: (x, b) => {
    if (x <= 0 || b <= 0) throw domain();
    const d = Math.log(b);
    if (d === 0) throw err("ZeroDivisionError", "division by zero");
    return Math.log(x) / d;
  },
  hypot: (a, b) => hypot(a, b),
  // a * b + z with one rounding: error-free product (Dekker), two-sum with z
  fma: (x, y, z) => {
    const cl = 134217729;
    const ax = x * cl, bx = y * cl;
    const xh = ax - (ax - x), xl = x - xh;
    const yh = bx - (bx - y), yl = y - yh;
    const p = x * y;
    const err = ((xh * yh - p) + xh * yl + xl * yh) + xl * yl;
    const s = p + z;
    const bv = s - p, av = s - bv;
    const del = (p - av) + (z - bv);
    return s + (del + err);
  },
  cbrt: (x) => Math.cbrt(x),
  degrees: (x) => x * (180 / Math.PI),
  radians: (x) => x * (Math.PI / 180),
  gamma: (x) => gamma(x),
  lgamma: (x) => lgamma(x),
  erf: (x) => erf(x),
  erfc: (x) => erfc(x),
  asinh: (x) => Math.asinh(x),
  acosh: (x) => {
    if (x < 1) throw floatArg("expected argument value not less than 1", x);
    return Math.acosh(x);
  },
  atanh: (x) => {
    if (Math.abs(x) >= 1) throw floatArg("expected a number between -1 and 1", x);
    return Math.atanh(x);
  },
  fsum_begin: () => {
    fsum = { p: [], special: 0, inf: 0 };
    return null;
  },
  fsum_add: (x) => fsumAdd(fsum, x),
  fsum_end: () => fsumEnd(fsum),
  int_truediv: (a, b) => intTruediv(a, b),
  nextafter: (x, y) => nextAfter(x, y),
  ulp: (x) => {
    x = Math.abs(x);
    if (!Number.isFinite(x)) return x;
    if (x === Number.MAX_VALUE) return x - nextAfter(x, -Infinity);
    return nextAfter(x, Infinity) - x;
  },
};

// math.hypot as CPython's vector_norm: scaled, squared exactly (fmaExact),
// one differential correction
function hypot(x, y) {
  x = Math.abs(x);
  y = Math.abs(y);
  if (x === Infinity || y === Infinity) return Infinity;
  if (Number.isNaN(x) || Number.isNaN(y)) return NaN;
  const max = Math.max(x, y);
  if (max === 0) return max;
  return vectorNorm([x, y], max);
}

function vectorNorm(v, max) {
  const DBL_MIN = 2.2250738585072014e-308;
  if (max < DBL_MIN) return DBL_MIN * vectorNorm(v.map((x) => x / DBL_MIN), max / DBL_MIN);
  const bits = new BigUint64Array(new Float64Array([max]).buffer)[0];
  const maxE = Number((bits >> 52n) & 0x7ffn) - 1022;
  const scale = 2 ** -maxE;
  let csum = 1.0, frac1 = 0.0, frac2 = 0.0;
  const add = (hi, lo) => {
    const s = csum + hi;
    const z = s - csum;
    frac2 += hi - z;
    csum = s;
    frac1 += lo;
  };
  for (let x of v) {
    x *= scale;
    const p = x * x;
    add(p, fmaExact(x, x, -p));
  }
  const h = Math.sqrt(csum - 1.0 + (frac1 + frac2));
  const p = -h * h;
  add(p, fmaExact(-h, h, -p));
  const x = csum - 1.0 + (frac1 + frac2);
  return (h + x / (2.0 * h)) / scale;
}

function nextAfter(x, y) {
  if (Number.isNaN(x) || Number.isNaN(y)) return NaN;
  if (x === y) return y;
  if (x === 0) return y > 0 ? 5e-324 : -5e-324;
  const f = new Float64Array([x]);
  const b = new BigInt64Array(f.buffer);
  b[0] += (y > x) === (x > 0) ? 1n : -1n;
  return f[0];
}

// a / b of ints beyond 2**53, as CPython: a quotient of 55 or 56 bits with a
// sticky last bit, rounded once by Number(), then scaled exactly
function intTruediv(a, b) {
  const neg = a < 0n !== b < 0n;
  if (a < 0n) a = -a;
  if (b < 0n) b = -b;
  const k = 55 - (a.toString(2).length - b.toString(2).length);
  const [n, d] = k >= 0 ? [a << BigInt(k), b] : [a, b << BigInt(-k)];
  let q = n / d;
  if (n % d !== 0n) q |= 1n;
  const x = Number(q) * 2 ** -k;
  return neg ? -x : x;
}

const floatArg = (msg, x) => err("ValueError", msg + ", got " + floatRepr(x));

// x * y + z rounded once: exact with BigInts, then rounded to nearest even
const fview = new DataView(new ArrayBuffer(8));
function parts(x) {
  fview.setFloat64(0, x);
  const bits = fview.getBigUint64(0);
  const ex = Number((bits >> 52n) & 0x7ffn);
  let m = bits & 0xfffffffffffffn;
  if (ex !== 0) m |= 1n << 52n;
  return [bits >> 63n ? -m : m, ex === 0 ? -1074 : ex - 1075];
}
function fmaExact(x, y, z) {
  if (!Number.isFinite(x) || !Number.isFinite(y) || x === 0 || y === 0) return x * y + z;
  if (!Number.isFinite(z)) return z;
  if (z === 0) return x * y; // the exact product is not zero: one rounding, sign kept
  const [mx, ex] = parts(x), [my, ey] = parts(y), [mz, ez] = parts(z);
  const ep = ex + ey, e = Math.min(ep, ez);
  const sum = ((mx * my) << BigInt(ep - e)) + (mz << BigInt(ez - e));
  if (sum === 0n) return 0;
  const neg = sum < 0n;
  let q = neg ? -sum : sum;
  const shift = Math.max(q.toString(2).length - 53, -1074 - e);
  let qe = e;
  if (shift > 0) {
    const b = BigInt(shift);
    const rem = q & ((1n << b) - 1n), half = 1n << (b - 1n);
    q >>= b;
    if (rem > half || (rem === half && (q & 1n) === 1n)) q += 1n;
    qe += shift;
  }
  const r = Number(q) * 2 ** qe;
  return neg ? -r : r;
}

// gamma and lgamma: CPython's Lanczos approximation (Modules/mathmodule.c). The C
// compiler fuses its `a * b + c` into fused multiply-adds (clang on arm64 does).
const LANCZOS_G = 6.024680040776729583740234375;
const LANCZOS_G_MINUS_HALF = 5.524680040776729583740234375;
const LANCZOS_NUM = [
  23531376880.410759688572007674451636754734846804940, 42919803642.649098768957899047001988850926355848959,
  35711959237.355668049440185451547166705960488635843, 17921034426.037209699919755754458931112671403265390,
  6039542586.3520280050642916443072979210699388420708, 1439720407.3117216736632230727949123939715485786772,
  248874557.86205415651146038641322942321632125127801, 31426415.585400194380614231628318205362874684987640,
  2876370.6289353724412254090516208496135991145378768, 186056.26539522349504029498971604569928220784236328,
  8071.6720023658162106380029022722506138218516325024, 210.82427775157934587250973392071336271166969580291,
  2.5066282746310002701649081771338373386264310793408,
];
const LANCZOS_DEN = [0, 39916800, 120543840, 150917976, 105258076, 45995730, 13339535, 2637558, 357423, 32670, 1925, 66, 1];
const GAMMA_INTEGRAL = [
  1, 1, 2, 6, 24, 120, 720, 5040, 40320, 362880, 3628800, 39916800, 479001600, 6227020800, 87178291200,
  1307674368000, 20922789888000, 355687428096000, 6402373705728000, 121645100408832000, 2432902008176640000,
  51090942171709440000, 1124000727777607680000,
];
const LOGPI = 1.144729885849400174143427351353058711647;
const NONINT = "expected a noninteger or positive integer";

function lanczosSum(x) {
  let num = 0, den = 0;
  if (x < 5) {
    for (let i = 12; i >= 0; i--) {
      num = fmaExact(num, x, LANCZOS_NUM[i]);
      den = fmaExact(den, x, LANCZOS_DEN[i]);
    }
  } else {
    for (let i = 0; i < 13; i++) {
      num = num / x + LANCZOS_NUM[i];
      den = den / x + LANCZOS_DEN[i];
    }
  }
  return num / den;
}

// C's round: halves away from zero
const roundC = (x) => Math.sign(x) * Math.floor(Math.abs(x) + 0.5);

function sinpi(x) {
  const y = Math.abs(x) % 2;
  let r;
  switch (roundC(2 * y)) {
    case 0: r = Math.sin(Math.PI * y); break;
    case 1: r = Math.cos(Math.PI * (y - 0.5)); break;
    case 2: r = Math.sin(Math.PI * (1 - y)); break;
    case 3: r = -Math.cos(Math.PI * (y - 1.5)); break;
    default: r = Math.sin(Math.PI * (y - 2));
  }
  return (x < 0 || Object.is(x, -0) ? -1 : 1) * r;
}

function gamma(x) {
  if (!Number.isFinite(x)) {
    if (Number.isNaN(x) || x > 0) return x;
    throw floatArg(NONINT, x);
  }
  if (x === Math.floor(x)) {
    if (x <= 0) throw floatArg(NONINT, x);
    if (x <= 23) return GAMMA_INTEGRAL[x - 1];
  }
  const absx = Math.abs(x);
  if (absx < 1e-20) return checked(1 / x, x);
  if (absx > 200) {
    if (x < 0) return 0 / sinpi(x);
    throw range();
  }
  const y = absx + LANCZOS_G_MINUS_HALF;
  let z = absx > LANCZOS_G_MINUS_HALF ? (y - absx) - LANCZOS_G_MINUS_HALF : (y - LANCZOS_G_MINUS_HALF) - absx;
  z = z * LANCZOS_G / y;
  let r;
  if (x < 0) {
    r = -Math.PI / sinpi(absx) / absx * Math.exp(y) / lanczosSum(absx);
    r = fmaExact(-z, r, r);
    if (absx < 140) {
      r /= Math.pow(y, absx - 0.5);
    } else {
      const s = Math.pow(y, absx / 2 - 0.25);
      r /= s;
      r /= s;
    }
  } else {
    r = lanczosSum(absx) / Math.exp(y);
    r = fmaExact(z, r, r);
    if (absx < 140) {
      r *= Math.pow(y, absx - 0.5);
    } else {
      const s = Math.pow(y, absx / 2 - 0.25);
      r *= s;
      r *= s;
    }
  }
  return checked(r, x);
}

function lgamma(x) {
  if (!Number.isFinite(x)) return Number.isNaN(x) ? x : Infinity;
  if (x === Math.floor(x) && x <= 2) {
    if (x <= 0) throw floatArg(NONINT, x);
    return 0;
  }
  const absx = Math.abs(x);
  if (absx < 1e-20) return -Math.log(absx);
  let r = Math.log(lanczosSum(absx)) - LANCZOS_G;
  r = fmaExact(absx - 0.5, Math.log(absx + LANCZOS_G - 0.5) - 1, r);
  if (x < 0) r = LOGPI - Math.log(Math.abs(sinpi(absx))) - Math.log(absx) - r;
  return checked(r, x);
}

// erf and erfc: FreeBSD's s_erf.c, as in most C libraries
const ERX = 8.45062911510467529297e-01, EFX8 = 1.02703333676410069053e+00;
const PP = [1.28379167095512558561e-01, -3.25042107247001499370e-01, -2.84817495755985104766e-02, -5.77027029648944159157e-03, -2.37630166566501626084e-05];
const QQ = [1, 3.97917223959155352819e-01, 6.50222499887672944485e-02, 5.08130628187576562776e-03, 1.32494738004321644526e-04, -3.96022827877536812320e-06];
const PA = [-2.36211856075265944077e-03, 4.14856118683748331666e-01, -3.72207876035701323847e-01, 3.18346619901161753674e-01, -1.10894694282396677476e-01, 3.54783043256182359371e-02, -2.16637559486879084300e-03];
const QA = [1, 1.06420880400844228286e-01, 5.40397917702171048937e-01, 7.18286544141962662868e-02, 1.26171219808761642112e-01, 1.36370839120290507362e-02, 1.19844998467991074170e-02];
const RA = [-9.86494403484714822705e-03, -6.93858572707181764372e-01, -1.05586262253232909814e+01, -6.23753324503260060396e+01, -1.62396669462573470355e+02, -1.84605092906711035994e+02, -8.12874355063065934246e+01, -9.81432934416914548592e+00];
const SA = [1, 1.96512716674392571292e+01, 1.37657754143519042600e+02, 4.34565877475229228821e+02, 6.45387271733267880336e+02, 4.29008140027567833386e+02, 1.08635005541779435134e+02, 6.57024977031928170135e+00, -6.04244152148580987438e-02];
const RB = [-9.86494292470009928597e-03, -7.99283237680523006574e-01, -1.77579549177547519889e+01, -1.60636384855821916062e+02, -6.37566443368389627722e+02, -1.02509513161107724954e+03, -4.83519191608651397019e+02];
const SB = [1, 3.03380607434824582924e+01, 3.25792512996573918826e+02, 1.53672958608443695994e+03, 3.19985821950859553908e+03, 2.55305040643316442583e+03, 4.74528541206955367215e+02, -2.24409524465858183362e+01];
const TINY = 2.2250738585072014e-308;

// c[0] + s * (c[1] + s * (... + s * c[n]))
function poly(c, s) {
  let r = c[c.length - 1];
  for (let i = c.length - 2; i >= 0; i--) r = c[i] + s * r;
  return r;
}

const f64 = new Float64Array(1);
const u32 = new Uint32Array(f64.buffer);
function highWord(x) {
  f64[0] = x;
  return u32[1];
}
function clearLowWord(x) {
  f64[0] = x;
  u32[0] = 0;
  return f64[0];
}

function erfc1(x) {
  const s = Math.abs(x) - 1;
  return 1 - ERX - poly(PA, s) / poly(QA, s);
}

function erfc2(ix, x) {
  if (ix < 0x3ff40000) return erfc1(x);
  x = Math.abs(x);
  const s = 1 / (x * x);
  const [r, q] = ix < 0x4006db6d ? [poly(RA, s), poly(SA, s)] : [poly(RB, s), poly(SB, s)];
  const z = clearLowWord(x);
  return Math.exp(-z * z - 0.5625) * Math.exp((z - x) * (z + x) + r / q) / x;
}

function erf(x) {
  const hx = highWord(x), sign = hx >>> 31, ix = hx & 0x7fffffff;
  if (ix >= 0x7ff00000) return 1 - 2 * sign + 1 / x;
  if (ix < 0x3feb0000) {
    if (ix < 0x3e300000) return 0.125 * (8 * x + EFX8 * x);
    const z = x * x;
    return x + x * (poly(PP, z) / poly(QQ, z));
  }
  const y = ix < 0x40180000 ? 1 - erfc2(ix, x) : 1 - TINY;
  return sign ? -y : y;
}

function erfc(x) {
  const hx = highWord(x), sign = hx >>> 31, ix = hx & 0x7fffffff;
  if (ix >= 0x7ff00000) return 2 * sign + 1 / x;
  if (ix < 0x3feb0000) {
    if (ix < 0x3c700000) return 1 - x;
    const z = x * x;
    const y = poly(PP, z) / poly(QQ, z);
    if (sign || ix < 0x3fd00000) return 1 - (x + x * y);
    return 0.5 - (x - 0.5 + x * y);
  }
  if (ix < 0x403c0000) return sign ? 2 - erfc2(ix, x) : erfc2(ix, x);
  return sign ? 2 - TINY : TINY * TINY;
}

// json.loads: the parser of pyrt (src/pyrt/lib/rupy_json.rs), with CPython's messages.
// A value is {k: "null" | "bool" | "int" | "float" | "str" | "list" | "dict", v};
// a dict's v is its [key, value] entries in order.
let jsonAt = [];
const jsonTop = () => jsonAt[jsonAt.length - 1];

function jsonText(j) {
  if (j.k === "float") return Number.isNaN(j.v) ? "NaN" : j.v === Infinity ? "Infinity" : j.v === -Infinity ? "-Infinity" : floatRepr(j.v);
  return String(j.v);
}

function jsonWant(k) {
  const j = jsonTop();
  if (j.k === k) return j;
  const what = j.k === "null" ? "null" : j.k === "list" || j.k === "dict" || j.k === "str" ? "a " + j.k : j.k + " " + jsonText(j);
  throw err("TypeError", "json.loads(): expected " + k + ", got " + what);
}

function jsonParse(src) {
  const s = [...src];
  let i = 0;
  const fail = (what, at) => {
    const before = s.slice(0, Math.min(at, s.length));
    const line = before.filter((c) => c === "\n").length + 1;
    const col = at - (before.lastIndexOf("\n") + 1) + 1;
    return err("ValueError", `${what}: line ${line} column ${col} (char ${at})`);
  };
  const ws = () => {
    while (i < s.length && " \t\n\r".includes(s[i])) i++;
  };
  const word = (w) => {
    const cs = [...w];
    if (cs.every((c, j) => s[i + j] === c)) {
      i += cs.length;
      return true;
    }
    return false;
  };
  const digit = (c) => c !== undefined && c >= "0" && c <= "9";
  const hex4 = () => {
    if (i + 4 > s.length) return null;
    const h = s.slice(i, i + 4).join("");
    if (!/^[0-9a-fA-F]{4}$/.test(h)) return null;
    i += 4;
    return parseInt(h, 16);
  };
  const char = (u) => (u >= 0xd800 && u < 0xe000 ? "\ufffd" : String.fromCodePoint(u));
  const string = () => {
    const start = i++;
    let out = "";
    for (;;) {
      if (i >= s.length) throw fail("Unterminated string starting at", start);
      const c = s[i++];
      if (c === '"') return out;
      if (c === "\\") {
        if (i >= s.length) throw fail("Unterminated string starting at", start);
        const e = s[i++];
        const simple = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" }[e];
        if (simple !== undefined) out += simple;
        else if (e === "u") {
          const u = hex4();
          if (u === null) throw fail("Invalid \\uXXXX escape", i - 1);
          if (u >= 0xd800 && u < 0xdc00 && s[i] === "\\" && s[i + 1] === "u") {
            const save = i;
            i += 2;
            const l = hex4();
            if (l !== null && l >= 0xdc00 && l < 0xe000) {
              out += String.fromCodePoint(0x10000 + ((u - 0xd800) << 10) + (l - 0xdc00));
              continue;
            }
            i = save;
          }
          out += char(u);
        } else throw fail("Invalid \\escape", i - 2);
      } else if (c.codePointAt(0) < 0x20) throw fail("Invalid control character at", i - 1);
      else out += c;
    }
  };
  const number = () => {
    const start = i;
    if (s[i] === "-") i++;
    if (s[i] === "0") i++;
    else if (digit(s[i])) while (digit(s[i])) i++;
    else throw fail("Expecting value", start);
    let float = false;
    if (s[i] === "." && digit(s[i + 1])) {
      float = true;
      i++;
      while (digit(s[i])) i++;
    }
    if (s[i] === "e" || s[i] === "E") {
      const save = i++;
      if (s[i] === "+" || s[i] === "-") i++;
      if (digit(s[i])) {
        float = true;
        while (digit(s[i])) i++;
      } else i = save;
    }
    const text = s.slice(start, i).join("");
    if (!float) {
      const n = BigInt(text);
      if (n >= I64_MIN && n <= I64_MAX) return { k: "int", v: n };
    }
    return { k: "float", v: Number(text) };
  };
  const value = () => {
    const start = i;
    const c = s[i];
    if (c === "{") return dict();
    if (c === "[") return list();
    if (c === '"') return { k: "str", v: string() };
    if (c === "n" && word("null")) return { k: "null", v: null };
    if (c === "t" && word("true")) return { k: "bool", v: true };
    if (c === "f" && word("false")) return { k: "bool", v: false };
    if (c === "N" && word("NaN")) return { k: "float", v: NaN };
    if (c === "I" && word("Infinity")) return { k: "float", v: Infinity };
    if (c === "-" && word("-Infinity")) return { k: "float", v: -Infinity };
    if (c === "-" || digit(c)) return number();
    throw fail("Expecting value", start);
  };
  const list = () => {
    i++;
    const v = [];
    ws();
    if (s[i] === "]") {
      i++;
      return { k: "list", v };
    }
    for (;;) {
      ws();
      v.push(value());
      ws();
      if (s[i] === ",") i++;
      else if (s[i] === "]") {
        i++;
        return { k: "list", v };
      } else throw fail("Expecting ',' delimiter", i);
    }
  };
  const dict = () => {
    i++;
    const m = new Map();
    const done = () => ({ k: "dict", v: [...m.entries()] });
    ws();
    if (s[i] === "}") {
      i++;
      return done();
    }
    for (;;) {
      ws();
      if (s[i] !== '"') throw fail("Expecting property name enclosed in double quotes", i);
      const k = string();
      ws();
      if (s[i] !== ":") throw fail("Expecting ':' delimiter", i);
      i++;
      ws();
      m.set(k, value());
      ws();
      if (s[i] === ",") i++;
      else if (s[i] === "}") {
        i++;
        return done();
      } else throw fail("Expecting ',' delimiter", i);
    }
  };
  ws();
  const v = value();
  ws();
  if (i < s.length) throw fail("Extra data", i);
  return v;
}

// math.fsum: Shewchuk's exact partial sums, rounded as CPython rounds them
let fsum = null;

function fsumAdd(st, x0) {
  const p = st.p;
  let x = x0, i = 0;
  for (let j = 0; j < p.length; j++) {
    let y = p[j];
    if (Math.abs(x) < Math.abs(y)) [x, y] = [y, x];
    const hi = x + y;
    const lo = y - (hi - x);
    if (lo !== 0) p[i++] = lo;
    x = hi;
  }
  p.length = i;
  if (x !== 0) {
    if (!Number.isFinite(x)) {
      if (Number.isFinite(x0)) throw err("OverflowError", "intermediate overflow in fsum");
      if (!Number.isNaN(x0)) st.inf += x0;
      st.special += x0;
      p.length = 0;
    } else {
      p.push(x);
    }
  }
  return null;
}

function fsumEnd(st) {
  if (st.special !== 0) {
    if (Number.isNaN(st.inf)) throw err("ValueError", "-inf + inf in fsum");
    return st.special;
  }
  const p = st.p;
  let n = p.length;
  if (n === 0) return 0;
  let hi = p[--n], lo = 0;
  while (n > 0) {
    const x = hi, y = p[--n];
    hi = x + y;
    lo = y - (hi - x);
    if (lo !== 0) break;
  }
  if (n > 0 && ((lo < 0 && p[n - 1] < 0) || (lo > 0 && p[n - 1] > 0))) {
    const y = lo * 2, x = hi + y;
    if (y === x - hi) hi = x;
  }
  return hi;
}

// ------------------------------------------------------------ str methods

const WS = /[\t\n\v\f\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u;
const isWs = (c) => WS.test(c);
const cps = (s) => [...s];
const num = (v) => Number(v);

function stripChars(s, chars, left, right) {
  const a = cps(s);
  const test = chars === undefined ? isWs : (c) => chars.includes(c);
  let i = 0, j = a.length;
  if (left) while (i < j && test(a[i])) i++;
  if (right) while (j > i && test(a[j - 1])) j--;
  return a.slice(i, j).join("");
}

function splitWs(s, max = -1) {
  const out = [];
  const a = cps(s);
  let i = 0;
  while (true) {
    while (i < a.length && isWs(a[i])) i++;
    if (i >= a.length) break;
    if (max >= 0 && out.length === max) {
      let rest = a.slice(i).join("");
      out.push(stripChars(rest, undefined, false, true));
      break;
    }
    let j = i;
    while (j < a.length && !isWs(a[j])) j++;
    out.push(a.slice(i, j).join(""));
    i = j;
  }
  return out;
}

function splitSep(s, sep, max = -1) {
  if (sep === "") throw err("ValueError", "empty separator");
  const out = [];
  let rest = s;
  while (max < 0 || out.length < max) {
    const i = rest.indexOf(sep);
    if (i < 0) break;
    out.push(rest.slice(0, i));
    rest = rest.slice(i + sep.length);
  }
  out.push(rest);
  return out;
}

function rsplitSep(s, sep, max = -1) {
  if (sep === "") throw err("ValueError", "empty separator");
  const out = [];
  let rest = s;
  while (max < 0 || out.length < max) {
    const i = rest.lastIndexOf(sep);
    if (i < 0) break;
    out.unshift(rest.slice(i + sep.length));
    rest = rest.slice(0, i);
  }
  out.unshift(rest);
  return out;
}

const LINE_BREAKS = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/u;

function splitlines(s, keep = false) {
  const out = [];
  let rest = s;
  while (rest.length) {
    const m = LINE_BREAKS.exec(rest);
    if (!m) {
      out.push(rest);
      break;
    }
    out.push(rest.slice(0, m.index + (keep ? m[0].length : 0)));
    rest = rest.slice(m.index + m[0].length);
  }
  return out;
}

/** index of a code unit offset → code point index */
const cpIndex = (s, i) => (i < 0 ? -1 : cps(s.slice(0, i)).length);

function countSub(s, sub) {
  if (sub === "") return cps(s).length + 1;
  let n = 0, i = 0;
  while ((i = s.indexOf(sub, i)) >= 0) {
    n++;
    i += sub.length;
  }
  return n;
}

const cased = (c) => c.toLowerCase() !== c.toUpperCase();

function title(s) {
  let out = "", prev = false;
  for (const c of s) {
    out += prev ? c.toLowerCase() : c.toUpperCase();
    prev = cased(c);
  }
  return out;
}

function justify(s, width, fill, how) {
  if (fill !== undefined && cps(fill).length !== 1) throw err("TypeError", "The fill character must be exactly one character long");
  fill = fill ?? " ";
  const n = num(width) - cps(s).length;
  if (n <= 0) return s;
  if (how === "l") return s + fill.repeat(n);
  if (how === "r") return fill.repeat(n) + s;
  // center: as CPython, the extra space goes left when the width is odd and n is odd
  const left = (n >> 1) + (n & num(width) & 1);
  return fill.repeat(left) + s + fill.repeat(n - left);
}

const STR = {
  upper: (s) => s.toUpperCase(),
  lower: (s) => s.toLowerCase(),
  casefold: (s) => s.toLowerCase().replace(/\u00df/g, "ss"),
  swapcase: (s) => cps(s).map((c) => (c === c.toUpperCase() ? c.toLowerCase() : c.toUpperCase())).join(""),
  title,
  capitalize: (s) => {
    const a = cps(s);
    return a.length ? a[0].toUpperCase() + a.slice(1).join("").toLowerCase() : "";
  },
  strip: (s, c) => stripChars(s, c, true, true),
  strip_chars: (s, c) => stripChars(s, c, true, true),
  lstrip_chars: (s, c) => stripChars(s, c, true, false),
  rstrip_chars: (s, c) => stripChars(s, c, false, true),
  split_max: (s, sep, max) => splitSep(s, sep, num(max)),
  replace_n: (s, a, b, n) => STR.replace(s, a, b, n),
  find_from: (s, sub, start) => {
    const a = cps(s);
    let i = num(start);
    if (i < 0) i = Math.max(0, i + a.length);
    if (i > a.length) return -1;
    const pre = a.slice(0, i).join("").length;
    return cpIndex(s, s.indexOf(sub, pre));
  },
  count_from: (s, sub, start) => {
    const a = cps(s);
    let i = num(start);
    if (i < 0) i = Math.max(0, i + a.length);
    if (i > a.length) return 0;
    return countSub(a.slice(i).join(""), sub);
  },
  center_fill: (s, w, f) => justify(s, w, f, "c"),
  ljust_fill: (s, w, f) => justify(s, w, f, "l"),
  rjust_fill: (s, w, f) => justify(s, w, f, "r"),
  lstrip: (s, c) => stripChars(s, c, true, false),
  rstrip: (s, c) => stripChars(s, c, false, true),
  split: (s, sep, max) => (sep === undefined ? splitWs(s) : splitSep(s, sep, max === undefined ? -1 : num(max))),
  split_ws: (s, max) => splitWs(s, max === undefined ? -1 : num(max)),
  split_ws_max: (s, max) => splitWs(s, num(max)),
  rsplit: (s, sep, max) => rsplitSep(s, sep, max === undefined ? -1 : num(max)),
  rsplit_all: (s, sep) => rsplitSep(s, sep),
  rsplit_max: (s, sep, max) => rsplitSep(s, sep, num(max)),
  splitlines: (s, keep) => splitlines(s, keep !== undefined && num(keep) !== 0),
  replace: (s, a, b, n) => {
    const max = n === undefined ? -1 : num(n);
    if (a === "") {
      const parts = cps(s);
      let out = "", k = 0;
      for (let i = 0; i <= parts.length; i++) {
        if (max < 0 || k < max) {
          out += b;
          k++;
        }
        if (i < parts.length) out += parts[i];
      }
      return out;
    }
    return max < 0 ? s.split(a).join(b) : splitSep(s, a, max).join(b);
  },
  startswith: (s, p) => s.startsWith(p),
  endswith: (s, p) => s.endsWith(p),
  find: (s, sub, start) => cpIndex(s, s.indexOf(sub, start === undefined ? 0 : cps(s).slice(0, num(start)).join("").length)),
  rfind: (s, sub) => cpIndex(s, s.lastIndexOf(sub)),
  rindex: (s, sub) => {
    const i = s.lastIndexOf(sub);
    if (i < 0) throw err("ValueError", "substring not found");
    return cpIndex(s, i);
  },
  count: (s, sub) => countSub(s, sub),
  isdigit: (s) => s !== "" && /^[\p{Nd}\u00b2\u00b3\u00b9\u2070-\u2079\u2080-\u2089\u2460-\u2468]+$/u.test(s),
  isdecimal: (s) => s !== "" && /^\p{Nd}+$/u.test(s),
  isnumeric: (s) => s !== "" && /^\p{N}+$/u.test(s),
  isalpha: (s) => s !== "" && /^\p{L}+$/u.test(s),
  isalnum: (s) => s !== "" && /^[\p{L}\p{N}]+$/u.test(s),
  isspace: (s) => s !== "" && cps(s).every(isWs),
  isupper: (s) => /\p{Lu}|\p{Lt}/u.test(s) && !/\p{Ll}/u.test(s),
  islower: (s) => /\p{Ll}/u.test(s) && !/\p{Lu}|\p{Lt}/u.test(s),
  istitle: (s) => s !== "" && title(s) === s && /\p{L}/u.test(s),
  isascii: (s) => /^[\x00-\x7f]*$/.test(s),
  isidentifier: (s) => /^[\p{L}_][\p{L}\p{N}_]*$/u.test(s),
  isprintable: (s) => !/[\p{C}\p{Z}]/u.test(s.replace(/ /g, "")),
  center: (s, w, f) => justify(s, w, f, "c"),
  ljust: (s, w, f) => justify(s, w, f, "l"),
  rjust: (s, w, f) => justify(s, w, f, "r"),
  zfill: (s, w) => {
    const n = num(w) - cps(s).length;
    if (n <= 0) return s;
    const sign = s[0] === "+" || s[0] === "-" ? s[0] : "";
    return sign + "0".repeat(n) + s.slice(sign.length);
  },
  partition: (s, sep) => {
    if (sep === "") throw err("ValueError", "empty separator");
    const i = s.indexOf(sep);
    return i < 0 ? [s, "", ""] : [s.slice(0, i), sep, s.slice(i + sep.length)];
  },
  rpartition: (s, sep) => {
    if (sep === "") throw err("ValueError", "empty separator");
    const i = s.lastIndexOf(sep);
    return i < 0 ? ["", "", s] : [s.slice(0, i), sep, s.slice(i + sep.length)];
  },
  removeprefix: (s, p) => (s.startsWith(p) ? s.slice(p.length) : s),
  removesuffix: (s, p) => (p && s.endsWith(p) ? s.slice(0, s.length - p.length) : s),
  expandtabs: (s, n) => {
    const size = n === undefined ? 8 : num(n);
    let out = "", col = 0;
    for (const c of s) {
      if (c === "\t") {
        const k = size > 0 ? size - (col % size) : 0;
        out += " ".repeat(k);
        col += k;
      } else {
        out += c;
        col = c === "\n" || c === "\r" ? 0 : col + 1;
      }
    }
    return out;
  },
};

// ------------------------------------------------------------ packages

// rupy_lib.wasm: the packages implemented in Rust (numpy, sklearn, torch, ...),
// built by `rupy wasm-lib`. A program that uses them exports `rupy_lib`; its
// package calls arrive as the operation `pkg` (a key, then argument tokens:
// BigInt, number or string) and their results are read back token by token.
const libModules = new Map();

/** The compiled rupy_lib.wasm: `lib` is bytes, a Module, or a URL / path (default: next to this file). */
async function libModule(lib) {
  if (lib instanceof WebAssembly.Module) return lib;
  if (lib instanceof Uint8Array || lib instanceof ArrayBuffer) return WebAssembly.compile(lib);
  let url = lib || (typeof process !== "undefined" && process.env?.RUPY_LIB_WASM) || new URL("rupy_lib.wasm", import.meta.url);
  url = String(url);
  if (!libModules.has(url)) {
    libModules.set(
      url,
      (async () => {
        if (/^[a-z]+:/i.test(url) && !url.startsWith("file:")) return WebAssembly.compileStreaming(fetch(url));
        const [fs, { fileURLToPath }] = await Promise.all([import("node:fs"), import("node:url")]);
        return WebAssembly.compile(fs.readFileSync(url.startsWith("file:") ? fileURLToPath(url) : url));
      })(),
    );
  }
  return libModules.get(url);
}

function encodeRequest(key, toks) {
  const parts = [enc.encode(key)];
  let size = 4 + parts[0].length;
  for (const t of toks) {
    if (typeof t === "string") {
      const b = enc.encode(t);
      parts.push(b);
      size += 5 + b.length;
    } else size += 9;
  }
  const buf = new Uint8Array(size);
  const dv = new DataView(buf.buffer);
  dv.setUint32(0, parts[0].length, true);
  buf.set(parts[0], 4);
  let at = 4 + parts[0].length;
  let si = 1;
  for (const t of toks) {
    if (typeof t === "bigint") {
      buf[at] = 0x69;
      dv.setBigInt64(at + 1, t, true);
      at += 9;
    } else if (typeof t === "number") {
      buf[at] = 0x66;
      dv.setFloat64(at + 1, t, true);
      at += 9;
    } else {
      const b = parts[si++];
      buf[at] = 0x73;
      dv.setUint32(at + 1, b.length, true);
      buf.set(b, at + 5);
      at += 5 + b.length;
    }
  }
  return buf;
}

function decodeResult(buf) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const out = [];
  let at = 0;
  while (at < buf.length) {
    const tag = buf[at];
    if (tag === 0x69) out.push(dv.getBigInt64(at + 1, true)), (at += 9);
    else if (tag === 0x66) out.push(dv.getFloat64(at + 1, true)), (at += 9);
    else {
      const n = dv.getUint32(at + 1, true);
      out.push(dec.decode(buf.subarray(at + 5, at + 5 + n)));
      at += 5 + n;
    }
  }
  return out;
}

// ------------------------------------------------------------- random

/** CPython's Mersenne Twister (the random module): the same seed gives the same numbers. */
class MersenneTwister {
  constructor() {
    const words = new Uint32Array(2);
    crypto.getRandomValues(words);
    this.seed((BigInt(words[0]) << 32n) | BigInt(words[1]));
  }

  initGenrand(s) {
    const mt = (this.mt = new Uint32Array(624));
    mt[0] = s;
    for (let i = 1; i < 624; i++) mt[i] = Math.imul(1812433253, mt[i - 1] ^ (mt[i - 1] >>> 30)) + i;
    this.index = 624;
  }

  /** random.seed(n) for an int: init_by_array with the 32-bit words of |n|. */
  seed(n) {
    let a = n < 0n ? -n : n;
    const key = [];
    while (a > 0n) {
      key.push(Number(a & 0xffffffffn));
      a >>= 32n;
    }
    if (!key.length) key.push(0);
    this.initGenrand(19650218);
    const mt = this.mt, N = 624;
    let i = 1, j = 0;
    for (let k = Math.max(N, key.length); k > 0; k--) {
      mt[i] = (mt[i] ^ Math.imul(mt[i - 1] ^ (mt[i - 1] >>> 30), 1664525)) + key[j] + j;
      i++;
      j++;
      if (i >= N) {
        mt[0] = mt[N - 1];
        i = 1;
      }
      if (j >= key.length) j = 0;
    }
    for (let k = N - 1; k > 0; k--) {
      mt[i] = (mt[i] ^ Math.imul(mt[i - 1] ^ (mt[i - 1] >>> 30), 1566083941)) - i;
      i++;
      if (i >= N) {
        mt[0] = mt[N - 1];
        i = 1;
      }
    }
    mt[0] = 0x80000000;
  }

  genrand() {
    const mt = this.mt;
    if (this.index >= 624) {
      for (let i = 0; i < 624; i++) {
        const y = (mt[i] & 0x80000000) | (mt[(i + 1) % 624] & 0x7fffffff);
        mt[i] = mt[(i + 397) % 624] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
      }
      this.index = 0;
    }
    let y = mt[this.index++];
    y ^= y >>> 11;
    y ^= (y << 7) & 0x9d2c5680;
    y ^= (y << 15) & 0xefc60000;
    return (y ^ (y >>> 18)) >>> 0;
  }

  random() {
    const a = this.genrand() >>> 5, b = this.genrand() >>> 6;
    return (a * 67108864 + b) * (1 / 9007199254740992);
  }

  /** getrandbits(k), k ≤ 64, as a BigInt */
  getrandbits(k) {
    if (k <= 32) return BigInt(this.genrand() >>> (32 - k));
    const lo = BigInt(this.genrand()), hi = BigInt(this.genrand() >>> (64 - k));
    return lo | (hi << 32n);
  }

  /** _randbelow(n) for a BigInt n */
  randbelow(n) {
    if (n <= 0n) return 0n;
    const k = n.toString(2).length;
    let r = this.getrandbits(k);
    while (r >= n) r = this.getrandbits(k);
    return r;
  }

  randrange(start, stop, step) {
    if (step === 1n) {
      if (start >= stop) throw err("ValueError", `empty range in randrange(${start}, ${stop})`);
      return start + this.randbelow(stop - start);
    }
    if (step === 0n) throw err("ValueError", "zero step for randrange()");
    const n = step > 0n ? (stop - start + step - 1n) / step : (stop - start + step + 1n) / step;
    if (n <= 0n) throw err("ValueError", "empty range in randrange()");
    return start + step * this.randbelow(n);
  }

  /** The indices random.sample(population of n, k) takes (CPython's set-or-pool selection). */
  sample(n, k) {
    if (k < 0n || k > BigInt(n)) throw err("ValueError", "Sample larger than population or is negative");
    k = Number(k);
    let setsize = 21;
    if (k > 5) {
      let p = 1;
      while (p < k * 3) p *= 4;
      setsize += p;
    }
    const out = [];
    if (n <= setsize) {
      const pool = Array.from({ length: n }, (_, i) => i);
      for (let i = 0; i < k; i++) {
        const j = Number(this.randbelow(BigInt(n - i)));
        out.push(pool[j]);
        pool[j] = pool[n - i - 1];
      }
    } else {
      const selected = new Set();
      for (let i = 0; i < k; i++) {
        let j = Number(this.randbelow(BigInt(n)));
        while (selected.has(j)) j = Number(this.randbelow(BigInt(n)));
        selected.add(j);
        out.push(j);
      }
    }
    return out;
  }
}

// ------------------------------------------------------------ the module's host

/**
 * Run a compiled program. `io.stdout` / `io.stderr` receive text; `io.stdin`
 * is the input text (or a function returning the next line, or null at the end).
 * `io.lib` is rupy_lib.wasm for programs that use packages implemented in Rust
 * (bytes, a Module, or a URL; default: next to this file). `io.files` holds the
 * files `open()` reads and writes: anything with get(path) → text | undefined and
 * set(path, text) (and delete(path), for os.remove), such as a Map (default: an
 * empty Map); `io.onFile(path, text)` is told of each file written, when it is
 * closed, and of each file removed (text null). `io.argv` is sys.argv
 * (default: ["main.py"]). Returns the exit code.
 */
export async function run(bytes, io = {}) {
  const stdout = io.stdout ?? ((s) => console.log(s));
  const stderr = io.stderr ?? ((s) => console.error(s));
  let lines = null;
  const nextLine = () => {
    if (typeof io.stdin === "function") return io.stdin();
    if (lines === null) {
      const text = io.stdin ?? "";
      lines = text.split(/(?<=\n)/);
      if (lines.length && lines[lines.length - 1] === "") lines.pop();
    }
    return lines.length ? lines.shift() : null;
  };
  let mem = null;
  let args = [];
  let pending = new Uint8Array(0);
  let list = [];
  let failed = 0;
  const str = (ptr, len) => dec.decode(new Uint8Array(mem.buffer, ptr, len));
  const setPending = (s) => {
    pending = enc.encode(s);
  };
  const ops = {
    float_repr: (x) => floatRepr(x),
    str_repr: (s) => pyRepr(s),
    format: (v, spec) => format(v, spec),
    int: (s, base) => parseInt64(s, num(base)),
    float: (s) => parseFloat64(s),
    ord: (s) => {
      const a = cps(s);
      if (a.length !== 1) throw err("TypeError", "ord() expected a character, but string of length " + a.length + " found");
      return BigInt(a[0].codePointAt(0));
    },
    chr: (i) => {
      if (i < 0n || i > 0x10ffffn) throw err("ValueError", "chr() arg not in range(0x110000)");
      return String.fromCodePoint(num(i));
    },
    input: () => {
      const l = nextLine();
      if (l === null || l === undefined) throw err("EOFError", "EOF when reading a line");
      return l.replace(/\r?\n$/, "");
    },
  };
  // open files: handle → { path, text, at (read position), write, dirty };
  // what is written reaches `files` when the file is closed (or the program ends)
  const files = io.files ?? new Map();
  const open = new Map();
  let nextHandle = 3;
  const file = (h, how) => {
    const f = open.get(h);
    if (!f) throw err("ValueError", "I/O operation on closed file.");
    if (how === "r" && f.write) throw err("OSError", "not readable");
    if (how === "w" && !f.write) throw err("OSError", "not writable");
    return f;
  };
  const save = (f) => {
    if (!f.dirty) return;
    f.dirty = false;
    files.set(f.path, f.text);
    io.onFile?.(f.path, f.text);
  };
  const readLine = (f) => {
    const i = f.text.indexOf("\n", f.at);
    const end = i < 0 ? f.text.length : i + 1;
    const line = f.text.slice(f.at, end);
    f.at = end;
    return line;
  };
  Object.assign(ops, {
    open: (path, mode) => {
      path = path.replace(/^(\.\/)+/, "");
      const m = mode.split(":")[0][0];
      let text = files.get(path);
      if (m === "r" && text === undefined) throw err("FileNotFoundError", `[Errno 2] No such file or directory: '${path}'`);
      if (m === "w") text = "";
      // universal newlines unless newline="" / "\n" (`:raw`)
      if (m === "r" && !mode.split(":").includes("raw")) text = text.replace(/\r\n?/g, "\n");
      const f = { path, text: text ?? "", at: 0, write: m !== "r", dirty: m !== "r" };
      open.set(BigInt(nextHandle), f);
      return BigInt(nextHandle++);
    },
    "file.read": (h) => {
      const f = file(h, "r");
      const s = f.text.slice(f.at);
      f.at = f.text.length;
      return s;
    },
    "file.readline": (h) => readLine(file(h, "r")),
    "file.readlines": (h) => {
      const f = file(h, "r");
      const out = [];
      while (f.at < f.text.length) out.push(readLine(f));
      return out;
    },
    "file.write": (h, s) => {
      const f = file(h, "w");
      f.text += s;
      f.dirty = true;
      return BigInt(cps(s).length);
    },
    "file.writelines": (h, ...lines) => {
      lines.pop(); // the count
      for (const s of lines) ops["file.write"](h, s);
      return null;
    },
    "file.close": (h) => {
      const f = open.get(h);
      if (f) save(f);
      open.delete(h);
      return null;
    },
  });
  const rng = new MersenneTwister();
  let sampled = [];
  Object.assign(ops, {
    "random.seed": (n) => (rng.seed(n), null),
    "random.random": () => rng.random(),
    "random.randbelow": (n) => rng.randbelow(n),
    "random.randrange": (a, b, step) => rng.randrange(a, b, step),
    "random.randint": (a, b) => rng.randrange(a, b + 1n, 1n),
    "random.uniform": (a, b) => a + (b - a) * rng.random(),
    "random.choice": (n) => {
      if (n === 0n) throw err("IndexError", "Cannot choose from an empty sequence");
      return rng.randbelow(n);
    },
    "random.sample": (n, k) => {
      sampled = rng.sample(Number(n), k);
      return null;
    },
    "random.sample_at": (i) => BigInt(sampled[Number(i)]),
  });
  const based = (n, base, prefix) => (n < 0n ? "-" : "") + prefix + (n < 0n ? -n : n).toString(base);
  Object.assign(ops, {
    "time.time": () => Date.now() / 1000,
    "sys.stderr_write": (s) => {
      stderr(s);
      return BigInt([...s].length);
    },
    // os.environ.get(key): [value] or [] (Node's environment; none in a browser)
    "os.environ_get": (k) => {
      const env = globalThis.process?.env ?? {};
      return Object.prototype.hasOwnProperty.call(env, k) ? [String(env[k])] : [];
    },
    // time.strftime(format) for the local time now, as pyrt's
    "time.strftime": (fmt) => {
      const t = new Date();
      const [y, mo, d, h, mi, s] = [t.getFullYear(), t.getMonth() + 1, t.getDate(), t.getHours(), t.getMinutes(), t.getSeconds()];
      const wd = (t.getDay() + 6) % 7;
      const yd = Math.round((Date.UTC(y, mo - 1, d) - Date.UTC(y, 0, 1)) / 86400000) + 1;
      const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
      const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
      const p = (n, w = 2) => String(n).padStart(w, "0");
      const f = {
        Y: String(y), y: p(y % 100), m: p(mo), d: p(d), H: p(h), I: p(h % 12 === 0 ? 12 : h % 12), M: p(mi), S: p(s),
        p: h < 12 ? "AM" : "PM", j: p(yd, 3), A: DAYS[wd], a: DAYS[wd].slice(0, 3), B: MONTHS[mo - 1],
        b: MONTHS[mo - 1].slice(0, 3), F: `${y}-${p(mo)}-${p(d)}`, T: `${p(h)}:${p(mi)}:${p(s)}`, "%": "%",
      };
      return fmt.replace(/%(.?)/gsu, (all, c) => (c === "" ? "%" : f[c] ?? all));
    },
    "time.perf_counter": () => performance.now() / 1000,
    "time.monotonic": () => performance.now() / 1000,
    "time.sleep": (s) => {
      const end = performance.now() + s * 1000;
      while (performance.now() < end); // a program runs synchronously
      return null;
    },
    // posixpath.join
    "os.path.join": (...parts) => {
      parts.pop(); // the count
      let path = "";
      for (const p of parts) path = p.startsWith("/") ? p : path === "" || path.endsWith("/") ? path + p : path + "/" + p;
      return path;
    },
    "os.path.exists": (p) => files.get(p.replace(/^(\.\/)+/, "")) !== undefined,
    "os.remove": (p) => {
      const path = p.replace(/^(\.\/)+/, "");
      if (files.get(path) === undefined || !files.delete) throw err("FileNotFoundError", `[Errno 2] No such file or directory: '${p}'`);
      files.delete(path);
      io.onFile?.(path, null);
      return null;
    },
    "sys.argv": () => io.argv ?? ["main.py"],
    "sys.stdin.readline": () => nextLine() ?? "",
    "sys.stdin.read": () => {
      let s = "";
      for (let l = nextLine(); l !== null && l !== undefined; l = nextLine()) s += l;
      return s;
    },
    // json.dumps of a str (ensure_ascii)
    "json.str": (s) => {
      let out = '"';
      for (const ch of s) {
        const c = ch.codePointAt(0);
        const esc = { '"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f" }[ch];
        if (esc) out += esc;
        else if (c < 0x20 || c > 0x7f) {
          const u = (x) => "\\u" + x.toString(16).padStart(4, "0");
          out += c > 0xffff ? u(0xd800 + ((c - 0x10000) >> 10)) + u(0xdc00 + ((c - 0x10000) & 0x3ff)) : u(c);
        } else out += ch;
      }
      return out + '"';
    },
    // json.loads: parse, then the program reads the value at the cursor by its type
    "json.loads": (s) => {
      jsonAt = [jsonParse(s)];
      return null;
    },
    "json.null": () => jsonTop().k === "null",
    "json.int": () => jsonWant("int").v,
    "json.float": () => jsonWant("float").v,
    "json.bool": () => jsonWant("bool").v,
    "json.text": () => jsonWant("str").v,
    "json.len": (dict) => BigInt(jsonWant(dict ? "dict" : "list").v.length),
    "json.key": (i) => jsonTop().v[Number(i)][0],
    "json.enter": (i) => {
      const t = jsonTop();
      jsonAt.push(t.k === "dict" ? t.v[Number(i)][1] : t.v[Number(i)]);
      return null;
    },
    "json.exit": () => {
      jsonAt.pop();
      return null;
    },
    bin: (n) => based(n, 2, "0b"),
    hex: (n) => based(n, 16, "0x"),
    oct: (n) => based(n, 8, "0o"),
  });
  // re: a pattern and a match are handles here; rupy_lib.wasm matches (the regex crate)
  let libCall = () => {
    throw new Error("rupy wasm host: re needs rupy_lib.wasm");
  };
  const patterns = [], pyPatterns = [], matches = [];
  let items = [];
  const pattern = (p) => (typeof p === "string" ? p : patterns[Number(p)]);
  /** The match encoded at out[at] (see rupy_lib's re_call) → [its handle, the next position]. */
  const readMatch = (out, at) => {
    const groups = [], names = new Map();
    for (let n = Number(out[at++]); n > 0; n--) {
      const [a, b, text] = [out[at++], out[at++], out[at++]];
      groups.push(a < 0n ? null : { start: a, end: b, text });
    }
    for (let n = Number(out[at++]); n > 0; n--) names.set(out[at++], Number(out[at++]));
    matches.push({ groups, names });
    return [BigInt(matches.length - 1), at];
  };
  const group = (h, i) => {
    const g = matches[Number(h)].groups;
    i = Number(i);
    if (i < 0 || i >= g.length) throw err("IndexError", "no such group");
    if (!g[i]) throw err("ValueError", `group ${i} did not take part in the match (Python gives None; not in the typed subset)`);
    return g[i];
  };
  Object.assign(ops, {
    "re.compile": (src, py) => {
      pyPatterns.push(py); // for its repr
      return BigInt(patterns.push(src) - 1);
    },
    "re.p_repr": (h) => "re.compile(" + pyRepr(pyPatterns[Number(h)]) + ")",
    "re.m_repr": (h) => {
      const m = group(h, 0);
      return `<re.Match object; span=(${m.start}, ${m.end}), match=${pyRepr(m.text)}>`;
    },
    "re.finditer": (p, s) => {
      const out = libCall("@re.finditer", [pattern(p), s]);
      items = [];
      let at = 1;
      for (let n = Number(out[0]); n > 0; n--) {
        const [h, next] = readMatch(out, at);
        items.push(h);
        at = next;
      }
      return BigInt(items.length);
    },
    "re.iter_at": (i) => items[Number(i)],
    "re.findall": (p, s) => libCall("@re.findall", [pattern(p), s]).slice(1),
    "re.split": (p, s) => libCall("@re.split", [pattern(p), s]).slice(1),
    "re.findall_groups": (p, s) => {
      const out = libCall("@re.findall_groups", [pattern(p), s]);
      const n = Number(out[0]), per = n ? (out.length - 1) / n : 0;
      items = Array.from({ length: n }, (_, i) => out.slice(1 + i * per, 1 + (i + 1) * per));
      return BigInt(n);
    },
    "re.row": (i) => items[Number(i)],
    "re.sub": (p, repl, s, count) => libCall("@re.sub", [pattern(p), repl, s, count])[0],
    "re.escape": (s) => [...s].map((c) => ("()[]{}?*+-|^$\\.&~# \t\n\r\x0b\x0c".includes(c) ? "\\" + c : c)).join(""),
    "re.m_group": (h, i) => group(h, i).text,
    "re.m_start": (h, i) => group(h, i).start,
    "re.m_end": (h, i) => group(h, i).end,
    "re.m_group_named": (h, name) => {
      const i = matches[Number(h)].names.get(name);
      if (i === undefined) throw err("IndexError", "no such group");
      return group(h, i).text;
    },
    "re.m_groups": (h) => matches[Number(h)].groups.slice(1).map((_, i) => group(h, i + 1).text),
  });
  for (const k of ["search", "match", "fullmatch"]) {
    ops["re." + k] = (p, s) => {
      const out = libCall("@re." + k, [pattern(p), s]);
      return out[0] < 0n ? -1n : readMatch(out, 0)[0];
    };
  }
  for (const [k, f] of Object.entries(MATH)) ops[k] = f;
  for (const [k, f] of Object.entries(STR)) ops["str." + k] = f;
  const invoke = () => {
    const name = args.pop();
    const a = args;
    args = [];
    failed = 0;
    const f = ops[name];
    if (!f) throw new Error("rupy wasm host: unknown operation " + name);
    try {
      return f(...a);
    } catch (e) {
      if (!(e instanceof PyErr)) throw e;
      failed = KINDS.indexOf(e.kind);
      setPending(e.msg);
      return null;
    }
  };
  const imports = {
    host: {
      write: (fd) => (fd === 2 ? stderr : stdout)(args.pop()),
      arg: (ptr, len) => args.push(str(ptr, len)),
      int_arg: (v) => args.push(v),
      float_arg: (v) => args.push(v),
      call: () => {
        const r = invoke();
        if (r === null) return 0n;
        if (typeof r === "string") {
          setPending(r);
          return 0n;
        }
        if (Array.isArray(r)) {
          list = r;
          return BigInt(r.length);
        }
        if (typeof r === "boolean") return r ? 1n : 0n;
        if (typeof r === "number") return BigInt(r);
        return r;
      },
      fcall: () => {
        const r = invoke();
        return r === null ? 0 : r;
      },
      pending: () => pending.length,
      take: (ptr) => new Uint8Array(mem.buffer, ptr, pending.length).set(pending),
      item: (i) => {
        setPending(list[i]);
        return pending.length;
      },
      failed: () => failed,
      r_int: () => 0n,
      r_float: () => 0,
      r_str: () => 0,
      track: () => null,
      free: () => {},
    },
  };
  const module = await WebAssembly.compile(bytes);
  if (WebAssembly.Module.exports(module).some((e) => e.name === "rupy_lib")) {
    const lib = (await WebAssembly.instantiate(await libModule(io.lib), {})).exports;
    let results = [];
    let at = 0;
    libCall = (key, toks) => {
      const req = encodeRequest(key, toks);
      const ptr = lib.rl_alloc(req.length); // may grow (and so replace) the memory
      new Uint8Array(lib.memory.buffer, ptr, req.length).set(req);
      const status = lib.rl_call();
      const out = decodeResult(new Uint8Array(lib.memory.buffer, lib.rl_out_ptr(), lib.rl_out_len()).slice());
      // the exception's chain (`LinAlgError,ValueError,...`): its nearest kind a program can catch
      if (status !== 0) throw err(out[0].split(",").find((k) => KINDS.includes(k)) ?? "RuntimeError", out[1]);
      return out;
    };
    ops.pkg = (key, ...toks) => {
      results = libCall(key, toks);
      at = 0;
      return null;
    };
    // a handle's token: when the program no longer holds the object, its handle is freed
    const registry = new FinalizationRegistry((id) => lib.rl_drop(id));
    imports.host.track = (id) => {
      const token = { id };
      registry.register(token, id, token);
      return token;
    };
    // freed by the program: forget the token (its id may be reused)
    imports.host.free = (id, token) => {
      registry.unregister(token);
      lib.rl_drop(id);
    };
    imports.host.r_int = () => results[at++];
    imports.host.r_float = () => results[at++];
    imports.host.r_str = () => {
      setPending(results[at++]);
      return pending.length;
    };
  }
  const instance = await WebAssembly.instantiate(module, imports);
  mem = instance.exports.mem;
  try {
    return instance.exports.run();
  } catch (e) {
    if (e instanceof RangeError && /call stack/i.test(e.message)) {
      stderr("Traceback (most recent call last):\nRecursionError: maximum recursion depth exceeded\n");
    } else {
      stderr("Traceback (most recent call last):\nRuntimeError: " + e.message + "\n");
    }
    return 1;
  } finally {
    for (const f of open.values()) save(f); // written but not closed: as at exit
  }
}

// node rupy_wasm.mjs prog.wasm < input
const isMain =
  typeof process !== "undefined" &&
  process.argv?.[1] &&
  (await (async () => {
    const [{ pathToFileURL }, fs] = await Promise.all([import("node:url"), import("node:fs")]);
    return import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href;
  })());
if (isMain) {
  const fs = await import("node:fs");
  const file = process.argv[2];
  if (!file) {
    console.error("usage: node rupy_wasm.mjs prog.wasm < input");
    process.exit(2);
  }
  let out = "";
  const flush = () => {
    if (out) fs.writeSync(1, out);
    out = "";
  };
  let input = null;
  const code = await run(fs.readFileSync(file), {
    argv: [file.replace(/\.wasm$/, ".py"), ...process.argv.slice(3)],
    files: {
      get: (p) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8") : undefined),
      set: (p, text) => fs.writeFileSync(p, text),
      delete: (p) => fs.unlinkSync(p),
    },
    stdout: (s) => {
      out += s;
      if (out.length > 65536) flush();
    },
    stderr: (s) => {
      flush();
      fs.writeSync(2, s);
    },
    stdin: () => {
      if (input === null) {
        try {
          input = fs.readFileSync(0, "utf8").split(/(?<=\n)/);
        } catch {
          input = [];
        }
      }
      return input.length ? input.shift() : null;
    },
  });
  flush();
  process.exitCode = code;
}
