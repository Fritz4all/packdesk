"""Phase 2 of the previous-webshop import: spare parts. Requests (part_tender) with their parts (part_request), the
answers' history, remarks, orders (part_order) with ordered parts, deliveries and corrections; then the
spare parts invoices are linked to their orders.

The previous webshop's Acer parts catalogue (part, part_price, part_model, ...) was last updated in 2009 and is not
imported; where a requested part came from it, its description is taken over.
"""

from collections import defaultdict
from decimal import Decimal

from django.utils.translation import gettext as _

from apps.invoices.models import Invoice
from apps.numbering import patterns
from apps.numbering.models import NumberSequence
from apps.orders.models import money
from apps.parts.models import (Correction, Delivery, DeliveryTime, PartOrder, PartOrderLine, PartRequest,
                               PaymentMethod, Remark, RequestLine, RequestLineChange)

DELIVERY_TIMES = {"instock": "in_stock", "days2to5": "days_2_5", "days6to10": "days_6_10",
                  "weeks2ormore": "weeks_2_more", "see_remark": "see_remark"}
PAYMENT_METHODS = {"1": "on_account", "2": "cash_on_delivery", "3": "proforma", "4": "ideal", "5": "bank_transfer"}
ORDER_STATUS = {"initial": PartOrder.Status.AWAITING_PAYMENT, "release": PartOrder.Status.AWAITING_APPROVAL,
                "deliver": PartOrder.Status.TO_DELIVER, "archive": PartOrder.Status.DONE}
PACKING = {"nieuw": "new", "pack": "pack", "refurbished": "refurbished"}
HUNDRED = Decimal("100")


def import_spare_parts(imp):
    from .importer import _aware, _date, _decimal, _keep_rank, _text

    def dec(value):
        return None if value in (None, "") else _decimal(value)

    imp.progress("spare parts")
    employees = imp.employees
    addresses = {_text(a["id"]): a for a in imp.rows("SELECT * FROM `part_address_delivery`")}

    def address(old_id):
        a = addresses.get(_text(old_id))
        if a is None:
            return {}
        return {"delivery_name": _text(a["name"]), "delivery_contact": _text(a["name_contact"]),
                "delivery_address": _text(a["line1"]), "delivery_postal_code": _text(a["zipcode"]),
                "delivery_city": _text(a["city"]), "delivery_country": _text(a["country"]),
                "delivery_phone": _text(a["telephone"])}

    def customer_and_user(employee_id):
        e = employees.get(_text(employee_id))
        if e is None:
            return None, None
        return imp.pk("customer", e["customer_id"]), imp.pk("user", e["user_id"])

    # Delivery times and payment methods: matched to PackDesk's own by their code.
    times = {t.code: t for t in DeliveryTime.objects.all()}
    imp.sync("spare parts settings", "part_deliver_time", DeliveryTime, imp.rows("SELECT * FROM `part_deliver_time`"),
             lambda r: ({"code": DELIVERY_TIMES.get(_text(r["name"]), _text(r["name"])[:32]),
                         "name": _text(r["description"]), "position": r["position"] or 0}, ""),
             name=lambda r, v: _text(r["description"]), match=lambda v: times.get(v["code"]),
             keep_on_update=("name", "position"))
    methods = {m.code: m for m in PaymentMethod.objects.all()}
    imp.sync("spare parts settings", "part_payment_type", PaymentMethod, imp.rows("SELECT * FROM `part_payment_type`"),
             lambda r: ({"code": PAYMENT_METHODS.get(_text(r["id"]), f"old_{r['id']}"), "name": _text(r["description"]),
                         "on_account": _text(r["id"]) == "1"}, ""),
             name=lambda r, v: _text(r["description"]), match=lambda v: methods.get(v["code"]),
             keep_on_update=("name", "on_account"))

    # Requests
    imp.progress("spare parts requests")
    tenders = imp.rows("SELECT * FROM `part_tender`")

    def request(t):
        customer_pk, user_pk = customer_and_user(t["employee_id"])
        if customer_pk is None:
            return None, "customer not found"
        return {"legacy_id": _text(t["id"]), "number": _text(t["number"]), "customer_id": customer_pk,
                "created_by_id": user_pk, "reference": _text(t["reference"]),
                "status": PartRequest.Status.ANSWERED if _text(t["status"]) == "complete" else PartRequest.Status.TO_HANDLE,
                "urgent": bool(t["fast"]), "urgent_possible": None if t["fast_possible"] is None else bool(t["fast_possible"]),
                "urgent_costs": dec(t["fast_costs"]), "valid_until": _date(t["valid_until"]),
                "created_at": _aware(t["created_at"]), **address(t["part_address_delivery_id"])}, ""

    imp.sync("spare parts requests", "part_tender", PartRequest, tenders, request, name=lambda t, v: _text(t["number"]))

    # Requested parts
    statuses = {_text(s["id"]): _text(s["name"]) for s in imp.rows("SELECT * FROM `part_request_status`")}
    time_names = {_text(t["id"]): DELIVERY_TIMES.get(_text(t["name"])) for t in imp.rows("SELECT * FROM `part_deliver_time`")}
    time_pks = {code: t.pk for code, t in ((t.code, t) for t in DeliveryTime.objects.all())}
    machines = {_text(m["part_request_id"]): m for m in imp.rows("SELECT * FROM `part_request_machine`")}
    catalogue = {_text(p["id"]): _text(p["description"]) for p in imp.rows("SELECT `id`, `description` FROM `part`")}
    vendors = set(imp.map["vendor"].values())

    def time(old_id):
        return time_pks.get(time_names.get(_text(old_id)))

    def line(r):
        request_pk = imp.pk("part_tender", r["part_tender_id"])
        if request_pk is None:
            return None, "request not found"
        m = machines.get(_text(r["id"]))
        vendor_pk = imp.pk("vendor", r["vendor_id"])
        description = _text(r["description"]) or catalogue.get(_text(r["part_id"]), "")
        status = statuses.get(_text(r["part_request_status_id"]), "open")
        return {"legacy_id": _text(r["id"]), "request_id": request_pk, "article_number": _text(r["number"]),
                "vendor_id": vendor_pk if vendor_pk in vendors else None, "quantity": r["count"] or 1,
                "description": description, "info": _text(r["info"]),
                "machine_model": _text(m["number"]) if m else "", "machine_serial": _text(m["number_serial"]) if m else "",
                "machine_description": _text(m["description"]) if m else "",
                "status": status if status in RequestLine.Status.values else RequestLine.Status.OPEN,
                "price_new": dec(r["price_new"]), "price_pack": dec(r["price_pack"]),
                "price_refurbished": dec(r["price_refurbished"]), "time_new_id": time(r["deliver_time_new"]),
                "time_pack_id": time(r["deliver_time_pack"]), "time_refurbished_id": time(r["deliver_time_refurbished"]),
                "created_at": _aware(r["created_at"])}, ""

    imp.sync("requested parts", "part_request", RequestLine, imp.rows("SELECT * FROM `part_request`"), line,
             name=lambda r, v: _text(r["number"]))

    imp.progress("spare parts history and remarks")

    def change(h):
        line_pk = imp.pk("part_request", h["part_request_id"])
        if line_pk is None:
            return None, "requested part not found"
        status = statuses.get(_text(h["part_request_status_id"]), "open")
        return {"legacy_id": _text(h["id"]), "line_id": line_pk, "user_id": imp.pk("user", h["user_id"]),
                "status": status if status in RequestLine.Status.values else RequestLine.Status.OPEN,
                "price_new": dec(h["price_new"]), "price_pack": dec(h["price_pack"]),
                "price_refurbished": dec(h["price_refurbished"]), "changed_at": _aware(h["created_at"])}, ""

    imp.sync("spare parts history", "part_request_history", RequestLineChange,
             imp.rows("SELECT * FROM `part_request_history`"), change, name=lambda h, v: _text(h["number"]))

    def remark(r):
        line_pk = imp.pk("part_request", r["part_request_id"])
        if line_pk is None:
            return None, "requested part not found"
        from_customer = bool(_text(r["employee_id"]))
        author = customer_and_user(r["employee_id"])[1] if from_customer else imp.pk("user", r["user_id"])
        return {"legacy_id": _text(r["id"]), "line_id": line_pk, "author_id": author, "from_customer": from_customer,
                "text": _text(r["content"]), "created_at": _aware(r["created_at"])}, ""

    imp.sync("spare parts remarks", "part_remark", Remark, imp.rows("SELECT * FROM `part_remark`"), remark,
             name=lambda r, v: _text(r["content"])[:40])

    # Orders, with their totals worked out the way the previous webshop did
    imp.progress("spare parts orders")
    ordered = defaultdict(list)
    ordered_rows = imp.rows("SELECT * FROM `part_ordered`")
    for o in ordered_rows:
        ordered[_text(o["part_order_id"])].append(o)
    method_pks = {m.code: m.pk for m in PaymentMethod.objects.all()}
    order_rows = imp.rows("SELECT * FROM `part_order`")
    # An order number used twice in the previous webshop: the later one gets "dup2" after it (as with licences).
    by_number = defaultdict(list)
    for o in order_rows:
        by_number[_text(o["number"])].append(o)
    renumbered = {}
    current = dict(PartOrder.objects.filter(pk__in=imp.map["part_order"].values()).values_list("pk", "number"))
    for number, group in by_number.items():
        group.sort(key=lambda o: (_keep_rank(current.get(imp.pk("part_order", o["id"])), number), str(o["created_at"]),
                                  _text(o["id"])))
        for i, o in enumerate(group[1:], 2):
            renumbered[_text(o["id"])] = f"{number}dup{i}"

    def order(o):
        customer_pk, user_pk = customer_and_user(o["employee_id"])
        request_pk = imp.pk("part_tender", o["part_tender_id"])
        if customer_pk is None or request_pk is None:
            return None, "customer or request not found"
        status = PartOrder.Status.CANCELLED if o["cancelled_at"] else ORDER_STATUS.get(_text(o["status"]),
                                                                                         PartOrder.Status.DONE)
        number = renumbered.get(_text(o["id"]), _text(o["number"]))
        values = {"legacy_id": _text(o["id"]), "number": number, "request_id": request_pk,
                  "customer_id": customer_pk, "created_by_id": user_pk, "created_at": _aware(o["created_at"]),
                  "reference": _text(o["reference"]), "status": status,
                  "payment_method_id": method_pks.get(PAYMENT_METHODS.get(_text(o["part_payment_type_id"]))),
                  "urgent": bool(o["fast"]), "being_picked": bool(o["processing_delivery"]),
                  "discount_pct": _decimal(o["margin"]), "urgent_costs": dec(o["fast_costs"]) or None,
                  "small_order_costs": dec(o["low_costs"]) if o["low"] else None,
                  "handling_costs": dec(o["handling_costs"]) or None, "payment_costs": dec(o["payment_costs"]) or None,
                  "delivery_costs": dec(o["delivery_costs"]) or None, "vat_rate": _decimal(o["tax_percentage"]),
                  "approved_at": _aware(o["released_at"]), "cancelled_at": _aware(o["cancelled_at"]),
                  **address(o["part_address_delivery_id"])}
        gross = money(sum((_decimal(p["price"]) * (p["count"] or 0) for p in ordered[_text(o["id"])]), Decimal("0")))
        discount = money(gross * values["discount_pct"] / HUNDRED)
        costs = sum((values[k] or Decimal("0") for k in ("urgent_costs", "small_order_costs", "handling_costs",
                                                         "payment_costs", "delivery_costs")), Decimal("0"))
        net = gross - discount + costs
        vat = money(net * values["vat_rate"] / HUNDRED)
        values.update(gross=gross, discount=discount, net=net, vat=vat, total=net + vat)
        note = f"number {o['number']} occurs more than once; imported as {number}" if number != _text(o["number"]) else ""
        if o["price"] is not None and abs(_decimal(o["price"]) - values["total"]) > Decimal("0.05"):
            note = "; ".join(filter(None, [note, f"total {values['total']} differs from the previous webshop's {o['price']}"]))
        return values, note

    imp.sync("spare parts orders", "part_order", PartOrder, order_rows, order,
             name=lambda o, v: _text(o["number"]))

    def ordered_line(p):
        order_pk, line_pk = imp.pk("part_order", p["part_order_id"]), imp.pk("part_request", p["part_request_id"])
        if order_pk is None or line_pk is None:
            return None, "order or requested part not found"
        return {"legacy_id": _text(p["id"]), "order_id": order_pk, "request_line_id": line_pk,
                "packing": PACKING.get(_text(p["packing"]), "new"), "quantity": p["count"] or 0,
                "purchase_price": dec(p["price_original"]), "unit_price": _decimal(p["price"]),
                "created_at": _aware(p["created_at"])}, ""

    imp.sync("ordered parts", "part_ordered", PartOrderLine, ordered_rows, ordered_line,
             name=lambda p, v: _text(p["packing"]))

    imp.progress("spare parts deliveries")
    for table, part, model in (("part_delivered", "deliveries", Delivery), ("part_correct", "corrections", Correction)):
        def movement(r, model=model):
            line_pk = imp.pk("part_ordered", r["part_ordered_id"])
            if line_pk is None:
                return None, "ordered part not found"
            values = {"legacy_id": _text(r["id"]), "line_id": line_pk, "quantity": r["amount"] or 0,
                      "user_id": imp.pk("user", r["user_id"]), "created_at": _aware(r["created_at"])}
            return values, "parts taken back" if values["quantity"] < 0 else ""

        imp.sync(part, table, model, imp.rows(f"SELECT * FROM `{table}`"), movement, name=lambda r, v: str(r["amount"]))

    # Spare parts invoices → their order; invoices without a PDF get the order's totals.
    imp.progress("spare parts invoices")
    rows = imp.rows("SELECT `id`, `invoice_id`, `part_order_id` FROM `invoice` WHERE `part_order_id` IS NOT NULL "
                    "AND `part_order_id` <> ''")
    orders = PartOrder.objects.in_bulk(list(imp.map["part_order"].values()))
    invoices = Invoice.objects.in_bulk([pk for pk in (imp.pk("invoice", r["id"]) for r in rows) if pk])
    taken = dict(Invoice.objects.exclude(part_order__isnull=True).values_list("part_order_id", "pk"))
    changed = []
    for r in rows:
        invoice, order = invoices.get(imp.pk("invoice", r["id"])), orders.get(imp.pk("part_order", r["part_order_id"]))
        if invoice is None or order is None:
            imp.report.add("spare parts invoices", "invoice", _text(r["id"]), "skipped", "invoice", "",
                           _text(r["invoice_id"]), "invoice or order not found")
            continue
        if taken.setdefault(order.pk, invoice.pk) != invoice.pk:
            imp.report.add("spare parts invoices", "invoice", _text(r["id"]), "skipped", "invoice", invoice.pk,
                           invoice.number, "order already has another invoice")
            continue
        fields = []
        if invoice.part_order_id != order.pk:
            invoice.part_order_id = order.pk
            fields.append("part_order")
        if not invoice.is_archive and not invoice.total:
            costs = sum((amount for _label, amount in order.costs()), Decimal("0"))
            for f, v in (("gross", order.gross + costs), ("discount_pct", order.discount_pct),
                         ("discount", order.discount), ("net", order.net), ("vat_rate", order.vat_rate),
                         ("vat", order.vat), ("total", order.total)):
                if getattr(invoice, f) != v:
                    setattr(invoice, f, v)
                    fields.append(f)
        if fields:
            changed.append(invoice)
        imp.report.add("spare parts invoices", "invoice", _text(r["id"]), "linked" if fields else "unchanged",
                       "invoice", invoice.pk, invoice.number, f"order {order.number}")
    Invoice.objects.bulk_update(changed, ["part_order", "gross", "discount_pct", "discount", "net", "vat_rate", "vat",
                                          "total"], batch_size=1000)

    # The request counter goes above the highest old request number.
    seq = NumberSequence.objects.filter(key="part_request").first()
    if seq:
        numbers = [n for n in (patterns.number_from(seq.pattern, v)
                               for v in PartRequest.objects.values_list("number", flat=True)) if n is not None]
        if numbers and seq.next_number <= max(numbers):
            if not imp.dry:
                seq.correct(max(numbers) + 1, imp.run.started_by, "Import vorige webshop: hoogste nummer + 1", max(numbers))
            imp.report.add("number counters", "number_sequence", "part_request", "updated", "number sequence", seq.pk,
                           "part_request", f"next number {seq.next_number} → {max(numbers) + 1}")

    imp.report.note(_("The old Acer parts catalogue (part, part_price, part_model, part_model_group, part_model_part, "
                      "part_type, part_stock) was last updated in 2009 and is not imported; descriptions of requested "
                      "parts from it are taken over."))
    imp.report.note(_("service_delivery_partner (delivery partners from 2009) is not used by PackDesk; not imported."))
