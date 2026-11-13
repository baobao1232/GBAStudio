def decompress_lz10(data, offset=0, max_output=32 * 1024 * 1024):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("LZ10 header is outside the ROM.")
    if data[offset] != 0x10:
        raise ValueError(f"Expected 0x10 marker, found {data[offset]:#04x}.")
    size = data[offset+1] | (data[offset+2] << 8) | (data[offset+3] << 16)
    if size == 0:
        raise ValueError("Declared output size is zero.")
    if size > max_output:
        raise ValueError(f"Output size {size:,} exceeds safety limit.")
    src = offset + 4
    out = bytearray()
    while len(out) < size:
        if src >= len(data):
            raise ValueError("Unexpected end of ROM at flag byte.")
        flags = data[src]
        src += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                if src + 2 > len(data):
                    raise ValueError("Unexpected end of ROM in back-reference.")
                b1, b2 = data[src], data[src+1]
                src += 2
                length = (b1 >> 4) + 3
                distance = (((b1 & 0x0F) << 8) | b2) + 1
                if distance > len(out):
                    raise ValueError("Invalid LZ10 back-reference.")
                for _ in range(length):
                    if len(out) >= size:
                        break
                    out.append(out[-distance])
            else:
                if src >= len(data):
                    raise ValueError("Unexpected end of ROM in literal.")
                out.append(data[src])
                src += 1
    return {"data": bytes(out), "consumed": src - offset, "declared_size": size}
