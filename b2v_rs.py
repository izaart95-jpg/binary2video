#!/usr/bin/env python3
# b2v_rs.py -- a small, self-contained Reed-Solomon codec over GF(256).
#
# Used by binary2video -y (platform-hardened mode) to protect the payload
# against symbol damage from lossy re-encoding (YouTube & friends).
#
# GF(2^8), primitive polynomial 0x11d, generator alpha = 2, fcr = 0.
# Codewords are "shortened": any data length 1..255-parity is legal, and a
# codeword is (parity_len + data_len) symbols long.
#
# Wire layout of one codeword (both sides agree):
#     cw[0 .. parity-1]  = parity symbols   (they ride x^0 .. x^(p-1))
#     cw[parity .. end]  = the data itself  (they ride x^p  .. x^(p+d-1))
#
#   rs_encode(data, parity)    -> codeword bytes   (parity first, data last)
#   rs_repair(cw, dlen)        -> (data_bytes, n_corrected) | RSUnfixable
#
# Pure stdlib, no dependencies.

__all__ = ["RSUnfixable", "rs_encode", "rs_repair"]


class RSUnfixable(Exception):
    pass


#--- Galois field ------------------------------------------------------------
GFEXP = [0] * 512
GFLOG = [0] * 256
_x = 1
for _i in range(255):
    GFEXP[_i] = _x
    GFLOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    GFEXP[_i] = GFEXP[_i - 255]


def gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return GFEXP[GFLOG[a] + GFLOG[b]]


def gf_inv(a):
    if a == 0:
        raise ZeroDivisionError("gf_inv(0)")
    return GFEXP[255 - GFLOG[a]]


def gf_pow(a, n):
    if a == 0:
        return 0
    return GFEXP[(GFLOG[a] * n) % 255]


# All polynomials below are coefficient lists with index == power
# (ascending, cw[0] rides x^0).
def poly_mul(p, q):
    out = [0] * (len(p) + len(q) - 1)
    for i, pi in enumerate(p):
        if pi:
            for j, qj in enumerate(q):
                if qj:
                    out[i + j] ^= gf_mul(pi, qj)
    return out


def poly_add(p, q):
    out = [0] * max(len(p), len(q))
    for i, pi in enumerate(p):
        out[i] ^= pi
    for i, qi in enumerate(q):
        out[i] ^= qi
    return out


def poly_eval(p, x):
    acc = 0
    for coef in reversed(p):          # Horner, highest power first
        acc = gf_mul(acc, x) ^ coef
    return acc


def poly_scaled_shift(p, coef, shift):
    out = [0] * (shift + len(p))
    for i, pi in enumerate(p):
        out[i + shift] = gf_mul(pi, coef)
    return out


_GEN_CACHE = {}


def generator_poly(parity):
    """g(x) = product of (x + alpha^i), i = 0..parity-1; monic, degree parity."""
    if parity not in _GEN_CACHE:
        g = [1]
        for i in range(parity):
            g = poly_mul(g, [gf_pow(2, i), 1])
        _GEN_CACHE[parity] = g
    return _GEN_CACHE[parity]


#--- encode ------------------------------------------------------------------
def rs_encode(data, parity):
    """Systematic encode. Codeword = remainder(x^(p..)) with data after it."""
    k = len(data)
    if not 1 <= k <= 255 - parity:
        raise ValueError(f"data length {k} out of range for parity {parity}")
    g = generator_poly(parity)
    work = [0] * parity + list(data)        # data riding x^p .. x^(p+k-1)
    for i in range(len(work) - 1, parity - 1, -1):
        c = work[i]
        if c:
            for j in range(parity):
                work[i - parity + j] ^= gf_mul(c, g[j])
            work[i] ^= c                    # g is monic: g[parity] == 1
    return bytes(work[:parity]) + bytes(data)


#--- decode ------------------------------------------------------------------
def _syndromes(cw, parity):
    return [poly_eval(cw, gf_pow(2, j)) for j in range(parity)]


def _berlekamp_massey(synd, parity):
    """Connection polynomial (ascending, [0]=1) with its error count."""
    C = [1]
    B = [1]
    L = 0
    m = 1
    b = 1
    for n in range(parity):
        d = synd[n]
        for i in range(1, L + 1):
            if i < len(C):
                d ^= gf_mul(C[i], synd[n - i])
        if d == 0:
            m += 1
        elif 2 * L <= n:
            T = list(C)
            C = poly_add(C, poly_scaled_shift(B, gf_mul(d, gf_inv(b)), m))
            L = n + 1 - L
            B = T
            b = d
            m = 1
        else:
            C = poly_add(C, poly_scaled_shift(B, gf_mul(d, gf_inv(b)), m))
            m += 1
    return C, L


def _chien(loc, n):
    """Codeword indices i with an error: locator root at alpha^-i."""
    positions = []
    for i in range(n):
        if poly_eval(loc, gf_pow(2, -i)) == 0:
            positions.append(i)
    return positions


def _forney(cw, synd, loc, positions):
    """Magnitudes via Forney (fcr = 0). Returns a corrected copy of cw."""
    parity = len(synd)
    omega = [0] * parity                     # S(x)*L(x) mod x^parity
    for i, si in enumerate(synd):
        if si:
            for j, lj in enumerate(loc):
                if i + j < parity and lj:
                    omega[i + j] ^= gf_mul(si, lj)
    fixed = list(cw)
    for i in positions:
        # X = alpha^i. Evaluate Omega and the derivative at X^-1.
        xinv = gf_pow(2, -i)
        num = poly_eval(omega, xinv)
        # formal derivative of loc in char 2: keep odd-index terms, x^(i-1)
        dnum = 0
        for j in range(1, len(loc), 2):
            if loc[j]:
                dnum ^= gf_mul(loc[j], gf_pow(xinv, j - 1))
        if dnum == 0:
            raise RSUnfixable("zero derivative at an error position")
        y = gf_mul(num, gf_inv(dnum))
        y = gf_mul(y, gf_inv(xinv))          # multiply by X = alpha^i
        fixed[i] ^= y
    return fixed


def rs_repair(cw, dlen):
    """Repair one codeword. Returns (data, n_corrected) or raises RSUnfixable."""
    parity = len(cw) - dlen
    if parity < 1 or 255 < len(cw) or dlen < 1:
        raise ValueError("bad block shape")
    synd = _syndromes(cw, parity)
    if not any(synd):
        return bytes(cw[parity:]), 0
    loc, nerr = _berlekamp_massey(synd, parity)
    positions = _chien(loc, len(cw))
    if len(positions) != nerr:
        raise RSUnfixable(f"locator degree {nerr}, chien found {len(positions)} roots")
    if nerr == 0:
        raise RSUnfixable("inconsistent locator")
    fixed = _forney(cw, synd, loc, positions)
    if any(_syndromes(fixed, parity)):       # hard proof of a true fix
        raise RSUnfixable("correction failed verification")
    return bytes(fixed[parity:]), len(positions)
