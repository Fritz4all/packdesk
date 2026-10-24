"""A small imitation of the previous webshop's database for tests: the tables and columns PackDesk reads,
with the same names as in the real schema, filled with invented data."""

import sqlite3

SCHEMA = [
    "CREATE TABLE `address` (`id` VARCHAR(36), `country` VARCHAR(64), `city` VARCHAR(64), `zipcode` VARCHAR(16), `line1` VARCHAR(255))",
    "CREATE TABLE `customer` (`id` VARCHAR(36), `name` VARCHAR(64), `number_deb` VARCHAR(32), `number_tax` VARCHAR(32), "
    "`telephone` VARCHAR(16), `email_packs` VARCHAR(255), `email_parts` VARCHAR(255), `email_invoice` VARCHAR(255), "
    "`margin_packs` DECIMAL(5,2), `margin_parts` DECIMAL(5,2), `skip_hw_support_pack_invoice` TINYINT, "
    "`activated` TINYINT, `deleted` TINYINT DEFAULT 0, `address` VARCHAR(36))",
    "CREATE TABLE `user` (`id` VARCHAR(36), `email` VARCHAR(255), `name_first` VARCHAR(64), `name_last` VARCHAR(64), `deleted` TINYINT DEFAULT 0)",
    "CREATE TABLE `employee` (`id` VARCHAR(36), `user_id` VARCHAR(36), `customer_id` VARCHAR(36), `telephone` VARCHAR(16), "
    "`function` VARCHAR(255), `department` VARCHAR(255), `deleted` TINYINT DEFAULT 0)",
    "CREATE TABLE `hw_support_order` (`id` INT, `employee_id` VARCHAR(36), `reference` VARCHAR(128), `discount` DECIMAL(5,2))",
    "CREATE TABLE `hw_support_order_entry` (`id` VARCHAR(36), `hw_support_order_id` VARCHAR(36))",
    "CREATE TABLE `hw_support_pack_license` (`id` VARCHAR(36), `hw_support_order_entry_id` VARCHAR(36), `prolongation_of` VARCHAR(36), "
    "`license_nr` VARCHAR(8), `license_nr_suffix` VARCHAR(4), `license_sequence_nr` INT, `registered_on` DATE, "
    "`start_date` DATE, `end_date` DATE, `description` VARCHAR(128), `product_nr` VARCHAR(64), `serial_nr` VARCHAR(64), "
    "`purchase_date` DATE, `email` VARCHAR(128), `reference` VARCHAR(128), `memo` VARCHAR(256))",
    "CREATE TABLE `hw_support_pack_license_option` (`id` VARCHAR(36), `hw_support_pack_license_id` VARCHAR(36), "
    "`serial_nr` VARCHAR(64), `product_nr` VARCHAR(64), `description` VARCHAR(128), `is_deleted` TINYINT DEFAULT 0)",
    "CREATE TABLE `invoice` (`id` INT, `invoice_id` VARCHAR(255), `payed_at` DATETIME, `hw_support_order_id` VARCHAR(36))",
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
