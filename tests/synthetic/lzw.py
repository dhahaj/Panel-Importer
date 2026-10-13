"""Unix ``compress`` (LZW, ``.Z``) encoder used to write compressed synthetic fixtures.

Mirrors the decoder behaviour of ``compress``/``unlzw3``: block mode, 9 to 16-bit codes,
and the historical padding of each code-width run to a multiple of ``bits`` bytes.
"""

from __future__ import annotations


def compress(data: bytes, maxbits: int = 16) -> bytes:
    out = bytearray(b"\x1f\x9d" + bytes([0x80 | maxbits]))
    if not data:
        return bytes(out)

    bits = 9
    end = 256  # last table entry as the decoder sees it (256 is CLEAR in block mode)
    emitted = 0
    run = bytearray()
    bitbuf = 0
    bitcnt = 0

    def flush_run(pad: bool) -> None:
        nonlocal bitbuf, bitcnt, run
        if bitcnt:
            run.append(bitbuf & 0xFF)
            bitbuf = 0
            bitcnt = 0
        if pad and len(run) % bits:
            run.extend(b"\0" * (bits - len(run) % bits))
        out.extend(run)
        run = bytearray()

    def emit(code: int) -> None:
        nonlocal bits, end, emitted, bitbuf, bitcnt
        if emitted:
            if end >= (1 << bits) - 1 and bits < maxbits:
                flush_run(pad=True)
                bits += 1
        bitbuf |= code << bitcnt
        bitcnt += bits
        while bitcnt >= 8:
            run.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bitcnt -= 8
        if emitted and end < (1 << bits) - 1:
            end += 1
        emitted += 1

    table = {bytes([i]): i for i in range(256)}
    next_code = 257
    max_code = (1 << maxbits) - 1
    w = data[:1]
    for byte in data[1:]:
        wc = w + bytes([byte])
        if wc in table:
            w = wc
            continue
        emit(table[w])
        if next_code <= max_code:
            table[wc] = next_code
            next_code += 1
        w = bytes([byte])
    emit(table[w])
    flush_run(pad=False)
    return bytes(out)
