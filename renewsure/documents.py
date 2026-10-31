"""Pure invoice-PDF rendering shared by HTTP downloads and email delivery."""


def pdf_invoice(i):
    lines = [
        "BRIGHTLOOP SOFTWARE / RENEWSURE",
        f"Invoice INV-{i['id']} | {i['state']}",
        f"Customer: {i['customer']}",
        f"Email: {i['email']}",
        f"Period: {i['period']} | Due: {i['due_date']}",
        "",
    ]
    for line in i["lines"]:
        lines.extend(
            [
                f"{line['description'][:60]} | {line['qty']} x INR {line['unit_price'] / 100:.2f}",
                f"Subtotal {line['subtotal'] / 100:.2f} - discount {line['discount'] / 100:.2f} + tax {line['tax'] / 100:.2f} = INR {line['total'] / 100:.2f}",
            ]
        )
    lines.extend(
        [
            "",
            f"Total: INR {i['total'] / 100:.2f}",
            f"Paid: INR {i['paid'] / 100:.2f}",
            f"Outstanding: INR {i['balance'] / 100:.2f}",
            "Configurable tax rules. This is not a GST compliance certificate.",
        ]
    )
    pages = [lines[n : n + 43] for n in range(0, len(lines), 43)]
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for page in pages:
        page_id = len(objects) + 1
        stream_id = page_id + 1
        kids.append(f"{page_id} 0 R")
        commands = ["BT /F1 11 Tf 48 790 Td 16 TL"]
        for s in page:
            commands.append(
                "("
                + s.encode("ascii", "replace")
                .decode()
                .replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
                + ") Tj T*"
            )
        commands.append("ET")
        stream = "\n".join(commands).encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    )
    out = b"%PDF-1.4\n"
    offsets = [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + b"".join(
        f"{o:010} 00000 n \n".encode() for o in offsets[1:]
    )
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out
