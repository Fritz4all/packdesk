"""Phase 3 of the previous-webshop import: printing services (kept as an archive) and telephony (catalogue and quotes).

Tables without an id of their own (ps_tender_entry, ps_consumable_order_item) get one made of the ids they
link, so a second run still recognises them.
"""

import re
from collections import defaultdict

from django.utils.translation import gettext as _

from apps.customers.models import Contact
from apps.printing.models import (Consumable, PrintContract, PrintContractLine, Printer, PrintQuote, PrintQuoteLine,
                                  SuppliesOrder, SuppliesOrderLine, SupportPlan)
from apps.telephony.models import Category, Item, Quote, QuoteLine, TelephonySettings


def import_printing(imp):
    from .importer import _aware, _date, _decimal, _text

    def dec(value):
        return None if value in (None, "") else _decimal(value)

    def customer_and_user(employee_id):
        e = imp.employees.get(_text(employee_id))
        return (imp.pk("customer", e["customer_id"]), imp.pk("user", e["user_id"])) if e else (None, None)

    vendors = set(imp.map["vendor"].values())

    def vendor(old_id):
        pk = imp.pk("vendor", old_id)
        return pk if pk in vendors else None

    imp.progress("printing services")
    types = {_text(t["id"]): t for t in imp.rows("SELECT * FROM `ps_support_type`")}
    imp.sync("printing catalogue", "ps_support", SupportPlan, imp.rows("SELECT * FROM `ps_support`"),
             lambda s: ({"legacy_id": _text(s["id"]), "years": s["duration"], "storage_factor": dec(s["storage_factor"]),
                         "lease_factor": dec(s["lease_factor"]), "position": s["position"] or 0,
                         "abbreviation": _text(types.get(_text(s["ps_support_type_id"]), {}).get("abbreviation")),
                         "description": _text(types.get(_text(s["ps_support_type_id"]), {}).get("description"))}, ""),
             name=lambda s, v: v.get("abbreviation", ""))

    printers = imp.rows("SELECT * FROM `ps_printer`")
    imp.sync("printing catalogue", "ps_printer", Printer, printers,
             lambda p: ({"legacy_id": _text(p["id"]), "name": _text(p["name"]), "product_nr": _text(p["product_nr"]),
                         "description": _text(p["description"]), "vendor_id": vendor(p["vendor_id"]),
                         "price": dec(p["price"]), "installation_costs": dec(p["installation_costs"]),
                         "support_factor": dec(p["support_factor"]), "color": bool(p["color"]),
                         "monthly_max_prints": p["monthly_max_prints"], "is_deleted": bool(p["is_deleted"])}, ""),
             name=lambda p, v: _text(p["name"]))
    links = [Printer(pk=imp.pk("ps_printer", p["id"]), successor_of_id=imp.pk("ps_printer", p["ps_printer_id"]))
             for p in printers if imp.pk("ps_printer", p["id"]) and imp.pk("ps_printer", p["ps_printer_id"])]
    Printer.objects.bulk_update(links, ["successor_of"])

    imp.sync("printing catalogue", "ps_consumable", Consumable, imp.rows("SELECT * FROM `ps_consumable`"),
             lambda c: ({"legacy_id": _text(c["id"]), "name": _text(c["name"]), "product_nr": _text(c["product_nr"]),
                         "vendor_id": vendor(c["vendor_id"]), "price": dec(c["price"]), "color": bool(c["color"]),
                         "prints": c["n_prints"], "user_replaceable": bool(c["user_replaceable"])}, ""),
             name=lambda c, v: _text(c["name"]))
    through = Consumable.printers.through
    wanted = {(imp.pk("ps_consumable", r["ps_consumable_id"]), imp.pk("ps_printer", r["ps_printer_id"]))
              for r in imp.rows("SELECT * FROM `ps_consumable_ps_printer`")}
    wanted = {pair for pair in wanted if all(pair)}
    have = set(through.objects.values_list("consumable_id", "printer_id"))
    through.objects.bulk_create([through(consumable_id=c, printer_id=p) for c, p in wanted - have])
    imp.report.counts["printing catalogue"]["linked"] += len(wanted - have)

    def prices(r):
        return {"options_price": dec(r["price_options"]), "total_prints": r["n_total_prints"],
                "color_prints": r["n_color_prints"], "price_ex_hw": dec(r["price_ex_hw"]),
                "price_inc_hw": dec(r["price_inc_hw"]), "customer_price_ex_hw": dec(r["cust_price_ex_hw"]),
                "customer_price_inc_hw": dec(r["cust_price_inc_hw"]), "price_print_black": dec(r["price_print_black"]),
                "price_print_color": dec(r["price_print_color"])}

    def quote(t):
        customer_pk, user_pk = customer_and_user(t["employee_id"])
        return {"legacy_id": _text(t["id"]), "number": _text(t["id"]), "customer_id": customer_pk,
                "created_by_id": user_pk, "reference": _text(t["reference"]),
                "margin_hardware": dec(t["margin_hardware"]), "margin_supplies": dec(t["margin_supplies"]),
                "margin_support": dec(t["margin_support"]), "margin_prints": dec(t["margin_prints"]),
                "deleted": bool(t["deleted"]), "created_at": _aware(t["created_at"])}, \
            "" if customer_pk else "customer not found"

    imp.sync("printing quotes", "ps_tender", PrintQuote, imp.rows("SELECT * FROM `ps_tender`"), quote,
             name=lambda t, v: _text(t["reference"]))
    entries = [{**r, "id": f"{r['ps_tender_id']}:{r['ps_printer_id']}"} for r in imp.rows("SELECT * FROM `ps_tender_entry`")]

    def quote_line(r):
        quote_pk = imp.pk("ps_tender", r["ps_tender_id"])
        if quote_pk is None:
            return None, "quote not found"
        return {"legacy_id": r["id"], "quote_id": quote_pk, "printer_id": imp.pk("ps_printer", r["ps_printer_id"]),
                "support_id": imp.pk("ps_support", r["ps_support_id"]), **prices(r)}, ""

    imp.sync("printing quotes", "ps_tender_entry", PrintQuoteLine, entries, quote_line, name=lambda r, v: "")

    addresses = {_text(a["id"]): a for a in imp.rows("SELECT * FROM `address`")}

    def contract(c):
        customer_pk, user_pk = customer_and_user(c["employee_id"])
        a = addresses.get(_text(c["address_id"]))
        address = ", ".join(filter(None, [_text(a["line1"]), f"{_text(a['zipcode'])} {_text(a['city'])}".strip(),
                                          _text(a["country"])])) if a else ""
        return {"legacy_id": _text(c["id"]), "number": f"{c['id']}{_text(c['id_suffix'])}",
                "quote_id": imp.pk("ps_tender", c["ps_tender_id"]), "customer_id": customer_pk,
                "created_by_id": user_pk, "company": _text(c["company"]),
                "contact": f"{_text(c['initials'])} {_text(c['lastname'])}".strip(), "phone": _text(c["phone_nr"]),
                "address": address, "start_date": _date(c["start_date"]), "end_date": _date(c["end_date"]),
                "preferred_date": _date(c["preferred_date"]), "includes_hardware": bool(c["inc_hardware"]),
                "activated_by_id": imp.pk("user", c["activated_by"]), "activated_at": _aware(c["activated_at"]),
                "created_at": _aware(c["created_at"])}, ""

    imp.sync("printing contracts", "ps_contract", PrintContract, imp.rows("SELECT * FROM `ps_contract`"), contract,
             name=lambda c, v: _text(c["company"]))
    readings = defaultdict(list)
    for m in imp.rows("SELECT * FROM `ps_printer_meta`"):
        when = _date(m["created_at"])
        readings[_text(m["ps_contract_entry_id"])].append(
            (f"{when:%d-%m-%Y} " if when else "") + f"{_text(m['name'])}: {_text(m['value'])}")

    def contract_line(r):
        contract_pk = imp.pk("ps_contract", r["ps_contract_id"])
        if contract_pk is None:
            return None, "contract not found"
        return {"legacy_id": _text(r["id"]), "contract_id": contract_pk, "printer_id": imp.pk("ps_printer", r["ps_printer_id"]),
                "support_id": imp.pk("ps_support", r["ps_support_id"]), "serial_nr": _text(r["serial_nr"]),
                "min_items": r["min_n_items"], "max_items": r["max_n_items"],
                "readings": "\n".join(readings.get(_text(r["id"]), [])), "created_at": _aware(r["created_at"]),
                **prices(r)}, ""

    imp.sync("printing contracts", "ps_contract_entry", PrintContractLine,
             imp.rows("SELECT * FROM `ps_contract_entry`"), contract_line, name=lambda r, v: _text(r["serial_nr"]))

    imp.sync("supplies orders", "ps_consumable_order", SuppliesOrder, imp.rows("SELECT * FROM `ps_consumable_order`"),
             lambda o: ({"legacy_id": _text(o["id"]), "number": f"{o['id']}{_text(o['id_suffix'])}",
                         "contract_line_id": imp.pk("ps_contract_entry", o["ps_contract_entry_id"]),
                         "contact": _text(o["contact"]), "sent_at": _aware(o["sent_at"]),
                         "sent_by_id": imp.pk("user", o["sent_by"]), "created_at": _aware(o["created_at"])}, ""),
             name=lambda o, v: _text(o["contact"]))
    items = [{**r, "id": f"{r['ps_consumable_order_id']}:{r['ps_consumable_id']}"}
             for r in imp.rows("SELECT * FROM `ps_consumable_order_item`")]

    def supplies_line(r):
        order_pk = imp.pk("ps_consumable_order", r["ps_consumable_order_id"])
        if order_pk is None:
            return None, "supplies order not found"
        return {"legacy_id": r["id"], "order_id": order_pk, "consumable_id": imp.pk("ps_consumable", r["ps_consumable_id"]),
                "quantity": r["amount"], "price": dec(r["price"])}, ""

    imp.sync("supplies orders", "ps_consumable_order_item", SuppliesOrderLine, items, supplies_line,
             name=lambda r, v: str(r["amount"]))
    imp.report.note(_("Printing services are kept as an archive: the previous webshop no longer offered them and its "
                      "calculation rules are not known, so PackDesk shows them but makes no new quotes. "
                      "ps_printer_option was empty."))


AUTO = re.compile(r"amount_sum_items\s+([\d,\s]+)")


def import_telephony(imp):
    from .importer import _aware, _decimal, _text

    def dec(value):
        return None if value in (None, "") else _decimal(value)

    imp.progress("telephony")
    imp.sync("telephony catalogue", "telephony_category", Category, imp.rows("SELECT * FROM `telephony_category`"),
             lambda c: ({"legacy_id": _text(c["id"]), "name": _text(c["name"]), "name_nl": _text(c["name"]),
                         "position": c["childnumber"] or 0}, ""),
             name=lambda c, v: _text(c["name"]), keep_on_update=("name", "name_nl"))
    rows = imp.rows("SELECT * FROM `telephony_item`")

    def item(i):
        category_pk = imp.pk("telephony_category", i["category_id"])
        if category_pk is None:
            return None, "category not found"
        return {"legacy_id": _text(i["id"]), "category_id": category_pk,
                "name": _text(i["description_short"]), "name_nl": _text(i["description_short"]),
                "description": _text(i["description_full"]), "description_nl": _text(i["description_full"]),
                "hire_per_month": dec(i["hire_costs_per_month"]) if i["has_hire_costs_per_month"] else None,
                "buy_price": dec(i["buy_costs"]) if i["has_buy_costs"] else None,
                "buy_per_month": dec(i["buy_costs_per_month"]) if i["has_buy_costs_per_month"] else None,
                "position": i["childnumber"] or 0}, ""

    imp.sync("telephony catalogue", "telephony_item", Item, rows, item, name=lambda i, v: _text(i["description_short"]),
             keep_on_update=("name", "name_nl", "description", "description_nl"))
    for i in rows:
        match = AUTO.search(_text(i["amount_function_on_calculator"]))
        pk = imp.pk("telephony_item", i["id"])
        if match and pk:
            sources = [imp.pk("telephony_item", n.strip()) for n in match.group(1).split(",") if n.strip()]
            Item.objects.get(pk=pk).quantity_from.set([s for s in sources if s])
    if any(_text(i["image_path"]) for i in rows):
        imp.report.note(_("Telephony item images were files on the old server and are not imported; add them in "
                          "the admin if needed."))

    for setting in imp.rows("SELECT * FROM `telephony_setting`"):
        if _text(setting["name"]) == "installation_costs":
            rules = TelephonySettings.load()
            rules.installation_costs = _decimal(setting["value"])
            rules.save()

    contacts = dict(Contact.objects.exclude(user__isnull=True).values_list("user_id", "customer_id"))

    def quote(t):
        user_pk = imp.pk("user", t["user_id"])
        return {"legacy_id": _text(t["id"]), "customer_id": contacts.get(user_pk), "created_by_id": user_pk,
                "reference": _text(t["reference"]),
                "view": Quote.View.RESELLER if _text(t["view"]) == "reseller" else Quote.View.CUSTOMER,
                "margin_hire": _decimal(t["margin_hire"]), "margin_buy": _decimal(t["margin_buy"]),
                "old_price_per_port": dec(t["price_per_port"]), "created_at": _aware(t["created_at"])}, \
            "" if contacts.get(user_pk) else "made by staff (no customer)"

    imp.sync("telephony quotes", "telephony_tender", Quote, imp.rows("SELECT * FROM `telephony_tender`"), quote,
             name=lambda t, v: _text(t["reference"]))

    def quote_line(r):
        quote_pk, item_pk = imp.pk("telephony_tender", r["telephony_tender_id"]), imp.pk("telephony_item", r["telephony_item_id"])
        if quote_pk is None or item_pk is None:
            return None, "quote or item not found"
        if not r["amount"]:
            return None, "quantity 0"
        return {"legacy_id": _text(r["id"]), "quote_id": quote_pk, "item_id": item_pk, "quantity": r["amount"],
                "hire_per_month": dec(r["hire_costs_per_month"]), "buy_price": dec(r["buy_costs"]),
                "buy_per_month": dec(r["buy_costs_per_month"])}, ""

    imp.sync("telephony quotes", "telephony_tender_item", QuoteLine, imp.rows("SELECT * FROM `telephony_tender_item`"),
             quote_line, name=lambda r, v: str(r["amount"]))
    imp.report.note(_("The telephony calculator is switched off until you switch it on under Telephony settings. "
                      "The previous webshop's price per port cannot be recalculated; old quotes show the stored value."))
