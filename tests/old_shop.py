"""A small imitation of the previous webshop's database for tests: the tables and columns PackDesk reads,
with the same names as in the real schema, filled with invented data."""

import sqlite3

SCHEMA = [
    "CREATE TABLE `address` (`id` VARCHAR(36), `country` VARCHAR(64), `city` VARCHAR(64), `zipcode` VARCHAR(16), `line1` VARCHAR(255))",
    "CREATE TABLE `customer` (`id` VARCHAR(36), `kind` VARCHAR(32), `name` VARCHAR(64), `number_deb` VARCHAR(32), "
    "`number_tax` VARCHAR(32), `telephone` VARCHAR(16), `fax` VARCHAR(16), `email_packs` VARCHAR(255), "
    "`email_parts` VARCHAR(255), `email_invoice` VARCHAR(255), `text_failure_24` TEXT, `text_failure_office` TEXT, "
    "`credit_parts` DECIMAL(8,2), `remark` TEXT, `margin_packs` DECIMAL(5,2), `margin_parts` DECIMAL(5,2), "
    "`margin_ps_hardware` DECIMAL(5,2), `margin_ps_support` DECIMAL(5,2), `margin_ps_supplies` DECIMAL(5,2), "
    "`margin_ps_prints` DECIMAL(5,2), `skip_hw_support_pack_invoice` TINYINT DEFAULT 0, `activated` TINYINT DEFAULT 1, "
    "`deleted` TINYINT DEFAULT 0, `address` VARCHAR(36), `address_invoice` VARCHAR(36), `address_delivery` VARCHAR(36), "
    "`contact` VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `user` (`id` VARCHAR(36), `login` VARCHAR(64), `crypted_password` VARCHAR(64), `salt` VARCHAR(64), "
    "`email` VARCHAR(255), `name_first` VARCHAR(64), `name_last` VARCHAR(64), `initials` VARCHAR(16), "
    "`last_login` DATETIME, `created_at` DATETIME, `deleted` TINYINT DEFAULT 0)",
    "CREATE TABLE `employee` (`id` VARCHAR(36), `user_id` VARCHAR(36), `customer_id` VARCHAR(36), `gender` VARCHAR(16), "
    "`telephone` VARCHAR(16), `function` VARCHAR(255), `department` VARCHAR(255), `remark` TEXT, `deleted` TINYINT DEFAULT 0)",
    "CREATE TABLE `role` (`id` VARCHAR(36), `name` VARCHAR(32))",
    "CREATE TABLE `user_role` (`user_id` VARCHAR(36), `role_id` VARCHAR(36))",
    "CREATE TABLE `hw_support_category` (`id` VARCHAR(36), `description` VARCHAR(255), `explanation` TEXT)",
    "CREATE TABLE `hw_class` (`id` VARCHAR(36), `name` VARCHAR(255), `explanation` TEXT, `position` INT)",
    "CREATE TABLE `vendor` (`id` VARCHAR(36), `name` VARCHAR(255), `product_nr_check` VARCHAR(128), "
    "`product_nr_description` VARCHAR(256), `real_vendor` TINYINT DEFAULT 1, `at_top` TINYINT DEFAULT 0)",
    "CREATE TABLE `hw_type` (`id` VARCHAR(36), `name` VARCHAR(64), `internal` TINYINT)",
    "CREATE TABLE `hw_support_category_hw_type` (`hw_support_category_id` VARCHAR(36), `hw_type_id` VARCHAR(36))",
    "CREATE TABLE `hw_system` (`id` VARCHAR(36), `vendor_id` VARCHAR(36), `hw_class_id` VARCHAR(36), `name` VARCHAR(64), "
    "`warranty` INT DEFAULT 0, `visible` TINYINT DEFAULT 1)",
    "CREATE TABLE `hw_support_period` (`id` VARCHAR(36), `duration` INT, `post_warranty` TINYINT)",
    "CREATE TABLE `hw_support_service` (`id` VARCHAR(36), `abbreviation` VARCHAR(10), `service` VARCHAR(40), "
    "`response` VARCHAR(20), `officehours` TINYINT)",
    "CREATE TABLE `hw_support_pack` (`id` VARCHAR(36), `hw_support_category_id` VARCHAR(36), `hw_support_service_id` VARCHAR(36), "
    "`hw_support_period_id` VARCHAR(36), `hw_class_id` VARCHAR(36), `price` DECIMAL(8,2), `enabled` TINYINT, "
    "`remark` VARCHAR(32), `code` VARCHAR(10), `abbreviation` VARCHAR(10), `monitor` TINYINT, "
    "`n_external_options` INT, `n_internal_options` INT, `registration_required` TINYINT)",
    "CREATE TABLE `hw_support_order` (`id` INT, `employee_id` VARCHAR(36), `boxes` TINYINT DEFAULT 0, "
    "`boxes_printed` TINYINT DEFAULT 0, `reference` VARCHAR(128), `discount` DECIMAL(5,2), `tax` DECIMAL(5,2), "
    "`company_name` VARCHAR(64), `company_contact` VARCHAR(128), `company_address` VARCHAR(128), "
    "`company_zipcode` VARCHAR(16), `company_city` VARCHAR(64), `created_at` DATETIME)",
    "CREATE TABLE `hw_support_order_entry` (`id` VARCHAR(36), `hw_support_order_id` VARCHAR(36), `hw_support_pack_id` VARCHAR(36), "
    "`hw_system_id` VARCHAR(36), `reference` VARCHAR(128), `n_packs` INT, `price_each` DECIMAL(8,2))",
    "CREATE TABLE `hw_support_pack_license` (`id` VARCHAR(36), `hw_support_order_entry_id` VARCHAR(36), `hw_system_id` VARCHAR(36), "
    "`prolongation_of` VARCHAR(36), `license_nr` VARCHAR(8), `license_nr_suffix` VARCHAR(4), `license_sequence_nr` INT, "
    "`registered_on` DATE, `start_date` DATE, `end_date` DATE, `description` VARCHAR(128), `product_nr` VARCHAR(64), "
    "`serial_nr` VARCHAR(64), `purchase_date` DATE, `email` VARCHAR(128), `reference` VARCHAR(128), `memo` VARCHAR(256), "
    "`hw_support_pack_license_reseller_id` VARCHAR(36))",
    "CREATE TABLE `hw_support_pack_license_reseller` (`id` VARCHAR(36), `name` VARCHAR(128), `phone` VARCHAR(16), "
    "`fax` VARCHAR(16), `address_id` VARCHAR(36))",
    "CREATE TABLE `hw_support_pack_license_option` (`id` VARCHAR(36), `hw_support_pack_license_id` VARCHAR(36), "
    "`vendor_id` VARCHAR(36), `hw_type_id` VARCHAR(36), `serial_nr` VARCHAR(64), `product_nr` VARCHAR(64), "
    "`description` VARCHAR(128), `created_at` DATETIME, `is_deleted` TINYINT DEFAULT 0)",
    "CREATE TABLE `part_order` (`id` VARCHAR(36), `reference` VARCHAR(255), `number` VARCHAR(64), `price` DECIMAL(8,2), "
    "`margin` DECIMAL(5,2), `fast` TINYINT, `fast_costs` DECIMAL(8,2), `low` TINYINT DEFAULT 0, `low_costs` DECIMAL(8,2), "
    "`payment_costs` DECIMAL(8,2), `delivery_costs` DECIMAL(8,2), `handling_costs` DECIMAL(8,2), "
    "`tax_percentage` DECIMAL(5,2), `released_at` DATETIME, `cancelled_at` DATETIME, `status` VARCHAR(64), "
    "`processing_delivery` TINYINT DEFAULT 0, `part_address_delivery_id` VARCHAR(36), `part_payment_type_id` INT, "
    "`part_tender_id` VARCHAR(36), `employee_id` VARCHAR(36), `created_at` DATETIME, `updated_at` DATETIME)",
    "CREATE TABLE `part_address_delivery` (`id` VARCHAR(36), `name` VARCHAR(255), `name_contact` VARCHAR(255), "
    "`line1` VARCHAR(255), `zipcode` VARCHAR(16), `city` VARCHAR(128), `country` VARCHAR(128), `telephone` VARCHAR(16), "
    "`fax` VARCHAR(16))",
    "CREATE TABLE `part_deliver_time` (`id` VARCHAR(36), `name` VARCHAR(32), `description` VARCHAR(255), `position` INT)",
    "CREATE TABLE `part_payment_type` (`id` INT, `description` VARCHAR(128))",
    "CREATE TABLE `part_request_status` (`id` VARCHAR(36), `name` VARCHAR(32), `description_bo` VARCHAR(128), "
    "`description_fo` VARCHAR(128))",
    "CREATE TABLE `part_tender` (`id` VARCHAR(36), `number` VARCHAR(32), `reference` TEXT, `fast` TINYINT, "
    "`fast_possible` TINYINT, `fast_costs` DECIMAL(8,2), `valid_until` DATE, `status` VARCHAR(64), "
    "`employee_id` VARCHAR(36), `part_address_delivery_id` VARCHAR(36), `created_at` DATETIME, `updated_at` DATETIME)",
    "CREATE TABLE `part_request` (`id` VARCHAR(36), `number` VARCHAR(64), `count` INT, `description` TEXT, `info` TEXT, "
    "`price_new` DECIMAL(8,2), `price_pack` DECIMAL(8,2), `price_refurbished` DECIMAL(8,2), `deliver_time_new` VARCHAR(36), "
    "`deliver_time_pack` VARCHAR(36), `deliver_time_refurbished` VARCHAR(36), `part_request_status_id` VARCHAR(36), "
    "`part_tender_id` VARCHAR(36), `vendor_id` VARCHAR(36), `part_id` VARCHAR(36), `created_at` DATETIME, "
    "`updated_at` DATETIME)",
    "CREATE TABLE `part_request_machine` (`id` VARCHAR(36), `number` VARCHAR(64), `number_serial` VARCHAR(64), "
    "`description` TEXT, `part_request_id` VARCHAR(36))",
    "CREATE TABLE `part_request_history` (`id` VARCHAR(36), `number` VARCHAR(255), `price_new` DECIMAL(8,2), "
    "`price_pack` DECIMAL(8,2), `price_refurbished` DECIMAL(8,2), `deliver_time_new` VARCHAR(36), "
    "`deliver_time_pack` VARCHAR(36), `deliver_time_refurbished` VARCHAR(36), `part_request_status_id` VARCHAR(36), "
    "`part_request_id` VARCHAR(36), `user_id` VARCHAR(36), `vendor_id` VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `part_remark` (`id` VARCHAR(36), `content` TEXT, `employee_id` VARCHAR(36), `user_id` VARCHAR(36), "
    "`part_request_id` VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `part_ordered` (`id` VARCHAR(36), `count` INT, `price_original` DECIMAL(8,2), `price` DECIMAL(8,2), "
    "`packing` VARCHAR(64), `part_request_id` VARCHAR(36), `part_order_id` VARCHAR(36), `created_at` DATETIME, "
    "`updated_at` DATETIME)",
    "CREATE TABLE `part_delivered` (`id` VARCHAR(36), `amount` INT, `part_ordered_id` VARCHAR(36), `user_id` VARCHAR(36), "
    "`created_at` DATETIME)",
    "CREATE TABLE `part_correct` (`id` VARCHAR(36), `amount` INT, `part_ordered_id` VARCHAR(36), `user_id` VARCHAR(36), "
    "`created_at` DATETIME)",
    "CREATE TABLE `part` (`id` VARCHAR(36), `number` VARCHAR(64), `description` VARCHAR(255), `vendor_id` VARCHAR(36), "
    "`part_type_id` VARCHAR(36))",
    "CREATE TABLE `invoice` (`id` INT, `invoice_id` VARCHAR(255), `payed_at` DATETIME, `created_at` DATETIME, "
    "`hw_support_order_id` VARCHAR(36), `part_order_id` VARCHAR(36))",
    "CREATE TABLE `invoice_payment` (`id` VARCHAR(36), `amount` DECIMAL(8,2), `created_at` DATETIME, `invoice_id` INT, "
    "`user_id` VARCHAR(36))",
    "CREATE TABLE `ps_consumable` (`id` VARCHAR(36), `product_nr` VARCHAR(32), `name` VARCHAR(48), `price` "
    "DECIMAL(8,2), `color` TINYINT, `n_prints` INT, `user_replaceable` TINYINT, `vendor_id` VARCHAR(36))",
    "CREATE TABLE `ps_consumable_order` (`id` INT, `id_suffix` VARCHAR(2), `contact` VARCHAR(64), `sent_at` "
    "DATETIME, `sent_by` VARCHAR(36), `ps_consumable_order_item_id` VARCHAR(36), `ps_contract_entry_id` "
    "VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `ps_consumable_order_item` (`ps_consumable_id` VARCHAR(36), `ps_consumable_order_id` VARCHAR(36), "
    "`amount` INT, `price` DECIMAL(8,2))",
    "CREATE TABLE `ps_consumable_ps_printer` (`ps_consumable_id` VARCHAR(36), `ps_printer_id` VARCHAR(36))",
    "CREATE TABLE `ps_contract` (`id` INT, `id_suffix` VARCHAR(3), `company` VARCHAR(128), `lastname` VARCHAR(64), "
    "`initials` VARCHAR(8), `gender` TINYINT, `phone_nr` VARCHAR(16), `start_date` DATE, `end_date` DATE, "
    "`preferred_date` DATE, `inc_hardware` TINYINT, `address_id` VARCHAR(36), `ps_tender_id` VARCHAR(36), "
    "`employee_id` VARCHAR(36), `activated_by` VARCHAR(36), `activated_at` DATETIME, `created_at` DATETIME)",
    "CREATE TABLE `ps_contract_entry` (`id` VARCHAR(36), `serial_nr` VARCHAR(40), `price_options` DECIMAL(8,2), "
    "`n_total_prints` INT, `n_color_prints` INT, `price_print_black` DECIMAL(5,4), `price_print_color` "
    "DECIMAL(5,4), `price_ex_hw` DECIMAL(8,2), `price_inc_hw` DECIMAL(8,2), `cust_price_ex_hw` DECIMAL(8,2), "
    "`cust_price_inc_hw` DECIMAL(8,2), `min_n_items` INT, `max_n_items` INT, `ps_support_id` VARCHAR(36), `user_id` "
    "VARCHAR(36), `ps_contract_id` INT, `ps_printer_id` VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `ps_printer` (`id` VARCHAR(36), `name` VARCHAR(48), `product_nr` VARCHAR(32), `description` "
    "VARCHAR(128), `price` DECIMAL(8,2), `installation_costs` DECIMAL(8,2), `support_factor` DECIMAL(5,4), `color` "
    "TINYINT, `monthly_max_prints` INT, `is_deleted` TINYINT, `ps_printer_id` VARCHAR(36), `vendor_id` VARCHAR(36))",
    "CREATE TABLE `ps_printer_meta` (`id` VARCHAR(36), `name` VARCHAR(32), `value` VARCHAR(32), "
    "`ps_contract_entry_id` VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `ps_printer_option` (`id` VARCHAR(36), `product_nr` VARCHAR(32), `amount` INT, `description` "
    "VARCHAR(128), `price` DECIMAL(8,2), `ps_contract_entry_id` VARCHAR(36), `created_at` DATETIME)",
    "CREATE TABLE `ps_support` (`id` VARCHAR(36), `duration` INT, `storage_factor` DECIMAL(5,4), `lease_factor` "
    "DECIMAL(8,6), `position` INT, `ps_support_type_id` VARCHAR(36))",
    "CREATE TABLE `ps_support_type` (`id` VARCHAR(36), `abbreviation` VARCHAR(8), `description` VARCHAR(128))",
    "CREATE TABLE `ps_tender` (`id` INT, `reference` VARCHAR(128), `margin_hardware` DECIMAL(5,2), "
    "`margin_supplies` DECIMAL(5,2), `margin_support` DECIMAL(5,2), `margin_prints` DECIMAL(5,2), `deleted` "
    "TINYINT, `created_at` DATETIME, `employee_id` VARCHAR(36))",
    "CREATE TABLE `ps_tender_entry` (`ps_tender_id` INT, `ps_printer_id` VARCHAR(36), `price_options` DECIMAL(8,2), "
    "`n_total_prints` INT, `n_color_prints` INT, `price_ex_hw` DECIMAL(8,2), `price_inc_hw` DECIMAL(8,2), "
    "`cust_price_ex_hw` DECIMAL(8,2), `cust_price_inc_hw` DECIMAL(8,2), `price_print_black` DECIMAL(5,4), "
    "`price_print_color` DECIMAL(5,4), `ps_support_id` VARCHAR(36))",
    "CREATE TABLE `telephony_category` (`id` INT, `childnumber` INT, `name` VARCHAR(256), `created_at` DATETIME, "
    "`updated_at` DATETIME)",
    "CREATE TABLE `telephony_item` (`id` INT, `childnumber` INT, `description_short` VARCHAR(256), "
    "`description_full` TEXT, `hire_costs_per_month` DECIMAL(8,2), `buy_costs` DECIMAL(8,2), "
    "`amount_function_on_calculator` VARCHAR(256), `image_path` VARCHAR(256), `category_id` INT, `created_at` "
    "DATETIME, `updated_at` DATETIME, `buy_costs_per_month` DECIMAL(8,2), `has_hire_costs_per_month` TINYINT, "
    "`has_buy_costs_per_month` TINYINT, `has_buy_costs` TINYINT)",
    "CREATE TABLE `telephony_setting` (`id` INT, `name` VARCHAR(255), `value` VARCHAR(255), `description` "
    "VARCHAR(255), `created_at` DATETIME, `updated_at` DATETIME)",
    "CREATE TABLE `telephony_tender` (`id` INT, `reference` VARCHAR(256), `view` VARCHAR(256), `price_per_port` "
    "DECIMAL(8,2), `margin_hire` DECIMAL(8,2), `user_id` VARCHAR(256), `created_at` DATETIME, `updated_at` "
    "DATETIME, `margin_buy` DECIMAL(8,2))",
    "CREATE TABLE `telephony_tender_item` (`id` INT, `telephony_tender_id` INT, `telephony_item_id` INT, `amount` "
    "INT, `hire_costs_per_month` DECIMAL(8,2), `created_at` DATETIME, `updated_at` DATETIME, `buy_costs_per_month` "
    "DECIMAL(8,2), `buy_costs` DECIMAL(8,2))",
]


def make_old_shop(path, data):
    """Create the SQLite file with rows: data = {table: [ {column: value} ]}."""
    conn = sqlite3.connect(path)
    for statement in SCHEMA:
        conn.execute(statement)
    for table, rows in data.items():
        for row in rows:
            columns = ", ".join(f"`{c}`" for c in row)
            conn.execute(f"INSERT INTO `{table}` ({columns}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    conn.commit()
    conn.close()
    return path
