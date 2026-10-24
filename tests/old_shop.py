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
    "CREATE TABLE `part_order` (`id` VARCHAR(36), `employee_id` VARCHAR(36))",
    "CREATE TABLE `invoice` (`id` INT, `invoice_id` VARCHAR(255), `payed_at` DATETIME, `created_at` DATETIME, "
    "`hw_support_order_id` VARCHAR(36), `part_order_id` VARCHAR(36))",
    "CREATE TABLE `invoice_payment` (`id` VARCHAR(36), `amount` DECIMAL(8,2), `created_at` DATETIME, `invoice_id` INT, "
    "`user_id` VARCHAR(36))",
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
