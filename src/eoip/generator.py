from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from faker import Faker

from .config import CompanyProfile


ENTITY_ORDER = [
    "customer",
    "product_category",
    "product",
    "warehouse",
    "salesperson",
    "supplier",
    "sales_order_header",
    "sales_order_line",
    "sales_invoice_header",
    "sales_invoice_line",
    "sales_credit_memo_header",
    "sales_credit_memo_line",
    "purchase_receipt_header",
    "purchase_receipt_line",
    "warehouse_transfer_header",
    "warehouse_transfer_line",
    "inventory_ledger_entry",
    "value_entry",
    "inventory_balance",
]


class ERPGenerator:
    def __init__(
        self,
        company: CompanyProfile,
        config: dict[str, Any],
        *,
        scale_factor: float | None = None,
    ) -> None:
        self.company = company
        self.config = config
        gen = config["generator"]
        self.seed = int(gen["seed"])
        self.scale_factor = float(scale_factor if scale_factor is not None else gen["scale_factor"])
        if self.scale_factor <= 0:
            raise ValueError("scale_factor must be greater than zero")

        self.rng = np.random.default_rng(self.seed)
        Faker.seed(self.seed)
        self.fake = Faker(gen.get("locale", "en_US"))
        self.fake.seed_instance(self.seed)

        self.end_date = pd.Timestamp(gen["end_date"]).normalize()
        self.history_months = int(gen["history_months"])
        self.start_date = (self.end_date - pd.DateOffset(months=self.history_months)) + pd.Timedelta(days=1)
        self.date_pool = pd.date_range(self.start_date, self.end_date, freq="D")
        self.date_probabilities = self._build_date_probabilities()

    def generate(self) -> dict[str, pd.DataFrame]:
        masters = self._generate_master_data()
        sales = self._generate_sales(masters)
        inventory = self._generate_inventory_and_cost(masters, sales)
        dataset = {**masters, **sales, **inventory}
        missing = [name for name in ENTITY_ORDER if name not in dataset]
        if missing:
            raise RuntimeError(f"Generator did not create required entities: {missing}")
        return {name: dataset[name] for name in ENTITY_ORDER}

    def _scaled(self, full_scale: int, minimum: int) -> int:
        return max(minimum, int(round(full_scale * self.scale_factor)))

    def _build_date_probabilities(self) -> np.ndarray:
        sales_cfg = self.config["generator"]["sales"]
        month_weights = {int(k): float(v) for k, v in sales_cfg["seasonal_month_weights"].items()}
        annual_growth = float(sales_cfg["annual_growth_rate"])
        day_weights = []
        for day in self.date_pool:
            year_index = max(0.0, (day - self.start_date).days / 365.25)
            growth = (1.0 + annual_growth) ** year_index
            day_weights.append(month_weights[int(day.month)] * growth)
        weights = np.asarray(day_weights, dtype=float)
        return weights / weights.sum()

    def _sample_dates(self, size: int) -> pd.DatetimeIndex:
        indices = self.rng.choice(len(self.date_pool), size=size, p=self.date_probabilities)
        return pd.DatetimeIndex(self.date_pool[indices]).sort_values()

    def _concentration_weights(self, size: int, alpha: float) -> np.ndarray:
        ranks = np.arange(1, size + 1, dtype=float)
        weights = 1.0 / np.power(ranks, alpha)
        permutation = self.rng.permutation(size)
        weights = weights[permutation]
        return weights / weights.sum()

    def _generate_master_data(self) -> dict[str, pd.DataFrame]:
        n_customers = self._scaled(self.company.customers, 30)
        n_products = self._scaled(self.company.products, 120)
        n_suppliers = self._scaled(self.company.suppliers, 12)
        n_warehouses = max(1, self.company.warehouse_locations)
        n_salespeople = max(6, min(40, int(math.ceil(n_customers / 120))))
        n_categories = max(8, min(30, int(round(math.sqrt(n_products)))))

        salesperson = pd.DataFrame(
            {
                "salesperson_id": [f"SP{i:04d}" for i in range(1, n_salespeople + 1)],
                "salesperson_code": [f"S{i:03d}" for i in range(1, n_salespeople + 1)],
                "display_name": [f"Commercial Team {i:02d}" for i in range(1, n_salespeople + 1)],
                "sales_region": [f"DE-{((i - 1) % 8) + 1}" for i in range(1, n_salespeople + 1)],
                "active_flag": True,
            }
        )

        supplier = pd.DataFrame(
            {
                "supplier_id": [f"SUP{i:05d}" for i in range(1, n_suppliers + 1)],
                "supplier_no": [f"V-{i:05d}" for i in range(1, n_suppliers + 1)],
                "supplier_name": [self.fake.company() for _ in range(n_suppliers)],
                "country_code": self.rng.choice(["DE", "NL", "BE", "PL", "CZ", "FR"], n_suppliers, p=[0.55, 0.12, 0.08, 0.10, 0.08, 0.07]),
                "default_lead_time_days": self.rng.integers(2, 35, n_suppliers),
                "active_flag": self.rng.random(n_suppliers) > 0.02,
            }
        )

        category_ids = [f"CAT{i:03d}" for i in range(1, n_categories + 1)]
        parents: list[str | None] = []
        for i in range(n_categories):
            if i < max(3, n_categories // 4):
                parents.append(None)
            else:
                parents.append(category_ids[int(self.rng.integers(0, max(1, n_categories // 4)))])
        product_category = pd.DataFrame(
            {
                "product_category_id": category_ids,
                "category_code": [f"C{i:03d}" for i in range(1, n_categories + 1)],
                "category_name": [f"Product Category {i:02d}" for i in range(1, n_categories + 1)],
                "parent_category_id": parents,
            }
        )

        warehouse = pd.DataFrame(
            {
                "warehouse_id": [f"WH{i:02d}" for i in range(1, n_warehouses + 1)],
                "warehouse_code": [f"W{i:02d}" for i in range(1, n_warehouses + 1)],
                "warehouse_name": [f"NordWerk Warehouse {i}" for i in range(1, n_warehouses + 1)],
                "region": [f"DE-{((i - 1) % 8) + 1}" for i in range(1, n_warehouses + 1)],
                "active_flag": True,
            }
        )

        customer_ids = [f"CUST{i:06d}" for i in range(1, n_customers + 1)]
        created_offsets = self.rng.integers(30, 3650, n_customers)
        customer = pd.DataFrame(
            {
                "customer_id": customer_ids,
                "customer_no": [f"K-{i:06d}" for i in range(1, n_customers + 1)],
                "customer_name": [self.fake.company() for _ in range(n_customers)],
                "customer_group": self.rng.choice(["Key Account", "Growth", "Standard", "Long Tail"], n_customers, p=[0.08, 0.17, 0.45, 0.30]),
                "country_code": self.rng.choice(["DE", "AT", "NL", "BE", "LU"], n_customers, p=[0.86, 0.05, 0.04, 0.03, 0.02]),
                "postal_region": [str(x) for x in self.rng.integers(1, 10, n_customers)],
                "salesperson_id": self.rng.choice(salesperson["salesperson_id"].to_numpy(), n_customers),
                "payment_terms_code": self.rng.choice(["14D", "30D", "45D", "60D"], n_customers, p=[0.12, 0.60, 0.20, 0.08]),
                "blocked_flag": self.rng.random(n_customers) < 0.01,
                "created_date": (self.start_date - pd.to_timedelta(created_offsets, unit="D")).date,
            }
        )

        base_price = np.clip(self.rng.lognormal(mean=3.8, sigma=0.85, size=n_products), 4.0, 2500.0)
        cost_ratio = self.rng.uniform(0.45, 0.78, n_products)
        created_product_offsets = self.rng.integers(15, 3000, n_products)
        product = pd.DataFrame(
            {
                "product_id": [f"PROD{i:06d}" for i in range(1, n_products + 1)],
                "product_no": [f"P-{i:06d}" for i in range(1, n_products + 1)],
                "product_name": [f"NordWerk Item {i:06d}" for i in range(1, n_products + 1)],
                "product_category_id": self.rng.choice(product_category["product_category_id"].to_numpy(), n_products),
                "base_unit_of_measure": self.rng.choice(["PCS", "BOX", "SET"], n_products, p=[0.83, 0.12, 0.05]),
                "standard_sales_price": np.round(base_price, 2),
                "standard_unit_cost": np.round(base_price * cost_ratio, 2),
                "preferred_supplier_id": self.rng.choice(supplier["supplier_id"].to_numpy(), n_products),
                "replenishment_lead_time_days": self.rng.integers(2, 42, n_products),
                "discontinued_flag": self.rng.random(n_products) < 0.025,
                "created_date": (self.start_date - pd.to_timedelta(created_product_offsets, unit="D")).date,
            }
        )

        return {
            "customer": customer,
            "product_category": product_category,
            "product": product,
            "warehouse": warehouse,
            "salesperson": salesperson,
            "supplier": supplier,
        }

    def _generate_sales(self, masters: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        cfg = self.config["generator"]
        sales_cfg = cfg["sales"]
        dist_cfg = cfg["distributions"]

        customers = masters["customer"]
        products = masters["product"]
        warehouses = masters["warehouse"]

        n_orders = self._scaled(int(sales_cfg["full_scale_order_target"]), 250)
        avg_lines = float(sales_cfg["average_lines_per_order"])
        invoice_rate = float(sales_cfg["invoice_rate"])
        return_rate = float(sales_cfg["return_line_rate"])
        tax_rate = float(sales_cfg["tax_rate"])

        customer_weights = self._concentration_weights(
            len(customers), float(dist_cfg["customer_concentration_alpha"])
        )
        product_weights = self._concentration_weights(
            len(products), float(dist_cfg["product_concentration_alpha"])
        )

        discount_map = {float(k): float(v) for k, v in dist_cfg["discount_probabilities"].items()}
        discount_values = np.asarray(list(discount_map.keys()), dtype=float)
        discount_probabilities = np.asarray(list(discount_map.values()), dtype=float)
        discount_probabilities = discount_probabilities / discount_probabilities.sum()

        order_dates = self._sample_dates(n_orders)
        customer_idx = self.rng.choice(len(customers), size=n_orders, p=customer_weights)
        customer_lookup = customers.set_index("customer_id")
        product_lookup = products.set_index("product_id")

        header_rows: list[dict[str, Any]] = []
        line_rows: list[dict[str, Any]] = []
        invoice_header_rows: list[dict[str, Any]] = []
        invoice_line_rows: list[dict[str, Any]] = []

        order_line_seq = 1
        invoice_seq = 1
        invoice_line_seq = 1

        for i in range(n_orders):
            order_id = f"SO{i + 1:07d}"
            order_no = f"SO-{i + 1:07d}"
            customer_id = customers.iloc[int(customer_idx[i])]["customer_id"]
            order_date = pd.Timestamp(order_dates[i])
            requested_delivery = min(
                order_date + pd.Timedelta(days=int(self.rng.integers(2, 15))),
                self.end_date + pd.Timedelta(days=30),
            )
            salesperson_id = customer_lookup.loc[customer_id, "salesperson_id"]
            invoiced = bool(
                (i == 0 or self.rng.random() < invoice_rate)
                and order_date <= self.end_date - pd.Timedelta(days=2)
            )
            line_count = max(1, int(self.rng.poisson(max(0.1, avg_lines - 1.0)) + 1))
            product_indices = self.rng.choice(len(products), size=line_count, p=product_weights)
            warehouse_indices = self.rng.integers(0, len(warehouses), size=line_count)

            order_net = 0.0
            current_order_lines: list[dict[str, Any]] = []
            for line_no, (pidx, widx) in enumerate(zip(product_indices, warehouse_indices), start=1):
                product_row = products.iloc[int(pidx)]
                quantity = max(1, int(round(self.rng.lognormal(mean=1.15, sigma=0.75))))
                base_price = float(product_row["standard_sales_price"])
                unit_price = round(max(0.5, base_price * float(self.rng.normal(1.0, 0.035))), 2)
                discount_pct = float(self.rng.choice(discount_values, p=discount_probabilities))
                gross = round(quantity * unit_price, 2)
                discount_amount = round(gross * discount_pct, 2)
                net = round(gross - discount_amount, 2)
                invoiced_qty = quantity if invoiced else 0
                outstanding_qty = quantity - invoiced_qty

                row = {
                    "sales_order_line_id": f"SOL{order_line_seq:09d}",
                    "sales_order_id": order_id,
                    "line_no": line_no * 10000,
                    "product_id": product_row["product_id"],
                    "warehouse_id": warehouses.iloc[int(widx)]["warehouse_id"],
                    "ordered_quantity": quantity,
                    "shipped_quantity": invoiced_qty,
                    "invoiced_quantity": invoiced_qty,
                    "outstanding_quantity": outstanding_qty,
                    "unit_price": unit_price,
                    "line_discount_pct": round(discount_pct * 100.0, 2),
                    "line_discount_amount": discount_amount,
                    "net_line_amount": net,
                    "promised_delivery_date": requested_delivery.date(),
                    "line_status": "invoiced" if invoiced else "open",
                }
                current_order_lines.append(row)
                line_rows.append(row)
                order_net += net
                order_line_seq += 1

            header_rows.append(
                {
                    "sales_order_id": order_id,
                    "order_no": order_no,
                    "customer_id": customer_id,
                    "order_date": order_date.date(),
                    "requested_delivery_date": requested_delivery.date(),
                    "salesperson_id": salesperson_id,
                    "currency_code": "EUR",
                    "status": "invoiced" if invoiced else "open",
                    "document_discount_amount": 0.0,
                    "created_at": (order_date + pd.Timedelta(hours=int(self.rng.integers(7, 18)))).isoformat(),
                }
            )

            if invoiced:
                invoice_id = f"SI{invoice_seq:07d}"
                invoice_no = f"INV-{invoice_seq:07d}"
                posting_date = min(
                    order_date + pd.Timedelta(days=int(self.rng.integers(1, 11))),
                    self.end_date,
                )
                invoice_net = 0.0

                for order_line in current_order_lines:
                    quantity = int(order_line["invoiced_quantity"])
                    gross = round(quantity * float(order_line["unit_price"]), 2)
                    discount_amount = round(float(order_line["line_discount_amount"]), 2)
                    net = round(gross - discount_amount, 2)
                    invoice_line_rows.append(
                        {
                            "sales_invoice_line_id": f"SIL{invoice_line_seq:09d}",
                            "sales_invoice_id": invoice_id,
                            "line_no": order_line["line_no"],
                            "source_order_no": order_no,
                            "source_order_line_no": order_line["line_no"],
                            "product_id": order_line["product_id"],
                            "warehouse_id": order_line["warehouse_id"],
                            "quantity": quantity,
                            "unit_price": order_line["unit_price"],
                            "gross_line_amount": gross,
                            "discount_amount": discount_amount,
                            "net_line_amount": net,
                        }
                    )
                    invoice_net += net
                    invoice_line_seq += 1

                invoice_header_rows.append(
                    {
                        "sales_invoice_id": invoice_id,
                        "invoice_no": invoice_no,
                        "customer_id": customer_id,
                        "invoice_date": posting_date.date(),
                        "posting_date": posting_date.date(),
                        "salesperson_id": salesperson_id,
                        "currency_code": "EUR",
                        "source_order_no": order_no,
                        "document_discount_amount": 0.0,
                        "total_net_amount": round(invoice_net, 2),
                        "total_tax_amount": round(invoice_net * tax_rate, 2),
                    }
                )
                invoice_seq += 1

        sales_order_header = pd.DataFrame(header_rows)
        sales_order_line = pd.DataFrame(line_rows)
        sales_invoice_header = pd.DataFrame(invoice_header_rows)
        sales_invoice_line = pd.DataFrame(invoice_line_rows)

        credit_header_rows: list[dict[str, Any]] = []
        credit_line_rows: list[dict[str, Any]] = []
        invoice_header_lookup = sales_invoice_header.set_index("sales_invoice_id")
        selected = self.rng.random(len(sales_invoice_line)) < return_rate
        if len(sales_invoice_line) > 0 and not bool(selected.any()):
            selected[int(self.rng.integers(0, len(sales_invoice_line)))] = True

        credit_seq = 1
        for _, invoice_line in sales_invoice_line.loc[selected].iterrows():
            quantity = int(invoice_line["quantity"])
            if quantity <= 0:
                continue
            max_return = max(1, int(math.ceil(quantity * 0.7)))
            return_qty = int(self.rng.integers(1, max_return + 1))
            gross_original = float(invoice_line["gross_line_amount"])
            discount_ratio = (
                float(invoice_line["discount_amount"]) / gross_original if gross_original > 0 else 0.0
            )
            gross_credit = round(return_qty * float(invoice_line["unit_price"]), 2)
            discount_amount = round(gross_credit * discount_ratio, 2)
            net_credit = round(gross_credit - discount_amount, 2)
            invoice_no = invoice_header_lookup.loc[invoice_line["sales_invoice_id"], "invoice_no"]
            customer_id = invoice_header_lookup.loc[invoice_line["sales_invoice_id"], "customer_id"]
            invoice_date = pd.Timestamp(
                invoice_header_lookup.loc[invoice_line["sales_invoice_id"], "posting_date"]
            )
            posting_date = min(
                invoice_date + pd.Timedelta(days=int(self.rng.integers(2, 45))),
                self.end_date,
            )
            credit_id = f"SCM{credit_seq:07d}"
            credit_no = f"CM-{credit_seq:07d}"
            disposition = str(self.rng.choice(["restock", "scrap", "financial_only"], p=[0.72, 0.18, 0.10]))

            credit_header_rows.append(
                {
                    "sales_credit_memo_id": credit_id,
                    "credit_memo_no": credit_no,
                    "customer_id": customer_id,
                    "posting_date": posting_date.date(),
                    "original_invoice_no": invoice_no,
                    "reason_code": str(self.rng.choice(["DAMAGED", "WRONG_ITEM", "QUALITY", "COMMERCIAL"], p=[0.28, 0.17, 0.25, 0.30])),
                    "total_net_amount": net_credit,
                }
            )
            credit_line_rows.append(
                {
                    "sales_credit_memo_line_id": f"SCML{credit_seq:09d}",
                    "sales_credit_memo_id": credit_id,
                    "line_no": 10000,
                    "original_invoice_no": invoice_no,
                    "original_invoice_line_no": int(invoice_line["line_no"]),
                    "product_id": invoice_line["product_id"],
                    "warehouse_id": invoice_line["warehouse_id"],
                    "return_quantity": return_qty,
                    "unit_price": float(invoice_line["unit_price"]),
                    "discount_amount": discount_amount,
                    "net_credit_amount": net_credit,
                    "disposition": disposition,
                }
            )
            credit_seq += 1

        sales_credit_memo_header = pd.DataFrame(credit_header_rows)
        sales_credit_memo_line = pd.DataFrame(credit_line_rows)

        for frame, columns in [
            (
                sales_credit_memo_header,
                [
                    "sales_credit_memo_id",
                    "credit_memo_no",
                    "customer_id",
                    "posting_date",
                    "original_invoice_no",
                    "reason_code",
                    "total_net_amount",
                ],
            ),
            (
                sales_credit_memo_line,
                [
                    "sales_credit_memo_line_id",
                    "sales_credit_memo_id",
                    "line_no",
                    "original_invoice_no",
                    "original_invoice_line_no",
                    "product_id",
                    "warehouse_id",
                    "return_quantity",
                    "unit_price",
                    "discount_amount",
                    "net_credit_amount",
                    "disposition",
                ],
            ),
        ]:
            if frame.empty:
                for column in columns:
                    frame[column] = pd.Series(dtype="object")
                frame = frame[columns]

        self._calibrate_sales_monetary_scale(
            masters,
            sales_order_line,
            sales_invoice_header,
            sales_invoice_line,
            sales_credit_memo_header,
            sales_credit_memo_line,
        )

        return {
            "sales_order_header": sales_order_header,
            "sales_order_line": sales_order_line,
            "sales_invoice_header": sales_invoice_header,
            "sales_invoice_line": sales_invoice_line,
            "sales_credit_memo_header": sales_credit_memo_header,
            "sales_credit_memo_line": sales_credit_memo_line,
        }

    def _calibrate_sales_monetary_scale(
        self,
        masters: dict[str, pd.DataFrame],
        sales_order_line: pd.DataFrame,
        sales_invoice_header: pd.DataFrame,
        sales_invoice_line: pd.DataFrame,
        sales_credit_memo_header: pd.DataFrame,
        sales_credit_memo_line: pd.DataFrame,
    ) -> None:
        invoice_net = float(sales_invoice_line["net_line_amount"].sum())
        credit_net = (
            float(sales_credit_memo_line["net_credit_amount"].sum())
            if not sales_credit_memo_line.empty
            else 0.0
        )
        current_net_sales = invoice_net - credit_net
        if current_net_sales <= 0:
            raise RuntimeError("Cannot calibrate sales because generated net sales are not positive.")

        history_years = max(1.0 / 12.0, (self.end_date - self.start_date).days / 365.25)
        target_net_sales = self.company.annual_revenue_eur * history_years * self.scale_factor
        factor = target_net_sales / current_net_sales

        product = masters["product"]
        for column in ["standard_sales_price", "standard_unit_cost"]:
            product[column] = (product[column].astype(float) * factor).round(2)

        for column in ["unit_price", "line_discount_amount", "net_line_amount"]:
            sales_order_line[column] = (sales_order_line[column].astype(float) * factor).round(2)

        for column in ["unit_price", "gross_line_amount", "discount_amount", "net_line_amount"]:
            sales_invoice_line[column] = (sales_invoice_line[column].astype(float) * factor).round(2)

        invoice_totals = (
            sales_invoice_line.groupby("sales_invoice_id", as_index=False)["net_line_amount"].sum()
        )
        invoice_totals["total_net_amount"] = invoice_totals["net_line_amount"].round(2)
        invoice_totals["total_tax_amount"] = (
            invoice_totals["total_net_amount"]
            * float(self.config["generator"]["sales"]["tax_rate"])
        ).round(2)
        sales_invoice_header.drop(
            columns=["total_net_amount", "total_tax_amount"],
            inplace=True,
        )
        recalibrated_headers = sales_invoice_header.merge(
            invoice_totals[["sales_invoice_id", "total_net_amount", "total_tax_amount"]],
            on="sales_invoice_id",
            how="left",
        )
        for column in recalibrated_headers.columns:
            sales_invoice_header[column] = recalibrated_headers[column]

        if not sales_credit_memo_line.empty:
            for column in ["unit_price", "discount_amount", "net_credit_amount"]:
                sales_credit_memo_line[column] = (
                    sales_credit_memo_line[column].astype(float) * factor
                ).round(2)

            credit_totals = (
                sales_credit_memo_line.groupby("sales_credit_memo_id", as_index=False)[
                    "net_credit_amount"
                ].sum()
            )
            credit_totals["total_net_amount"] = credit_totals["net_credit_amount"].round(2)
            sales_credit_memo_header.drop(columns=["total_net_amount"], inplace=True)
            recalibrated_credits = sales_credit_memo_header.merge(
                credit_totals[["sales_credit_memo_id", "total_net_amount"]],
                on="sales_credit_memo_id",
                how="left",
            )
            for column in recalibrated_credits.columns:
                sales_credit_memo_header[column] = recalibrated_credits[column]

    def _generate_inventory_and_cost(
        self,
        masters: dict[str, pd.DataFrame],
        sales: dict[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        inv_cfg = self.config["generator"]["inventory"]
        products = masters["product"]
        warehouses = masters["warehouse"]
        suppliers = masters["supplier"]

        product_lookup = products.set_index("product_id")
        n_receipts = self._scaled(int(inv_cfg["full_scale_purchase_receipt_target"]), 100)
        n_transfers = self._scaled(int(inv_cfg["full_scale_transfer_target"]), 25)

        receipt_header_rows: list[dict[str, Any]] = []
        receipt_line_rows: list[dict[str, Any]] = []
        receipt_line_seq = 1
        receipt_dates = self._sample_dates(n_receipts)

        product_weights = self._concentration_weights(
            len(products), float(self.config["generator"]["distributions"]["product_concentration_alpha"])
        )

        for i in range(n_receipts):
            receipt_id = f"PR{i + 1:07d}"
            receipt_no = f"REC-{i + 1:07d}"
            supplier_id = suppliers.iloc[int(self.rng.integers(0, len(suppliers)))]["supplier_id"]
            warehouse_id = warehouses.iloc[int(self.rng.integers(0, len(warehouses)))]["warehouse_id"]
            posting_date = pd.Timestamp(receipt_dates[i])
            receipt_header_rows.append(
                {
                    "purchase_receipt_id": receipt_id,
                    "receipt_no": receipt_no,
                    "supplier_id": supplier_id,
                    "warehouse_id": warehouse_id,
                    "posting_date": posting_date.date(),
                    "supplier_document_no": f"SUPDOC-{i + 1:08d}",
                }
            )
            line_count = int(self.rng.integers(1, 6))
            product_indices = self.rng.choice(len(products), size=line_count, p=product_weights)
            for line_no, pidx in enumerate(product_indices, start=1):
                product_row = products.iloc[int(pidx)]
                quantity = max(5, int(round(self.rng.lognormal(mean=3.8, sigma=0.65))))
                unit_cost = round(
                    max(
                        0.1,
                        float(product_row["standard_unit_cost"]) * float(self.rng.normal(1.0, 0.04)),
                    ),
                    2,
                )
                receipt_line_rows.append(
                    {
                        "purchase_receipt_line_id": f"PRL{receipt_line_seq:09d}",
                        "purchase_receipt_id": receipt_id,
                        "line_no": line_no * 10000,
                        "product_id": product_row["product_id"],
                        "quantity": quantity,
                        "unit_cost": unit_cost,
                    }
                )
                receipt_line_seq += 1

        purchase_receipt_header = pd.DataFrame(receipt_header_rows)
        purchase_receipt_line = pd.DataFrame(receipt_line_rows)

        transfer_header_rows: list[dict[str, Any]] = []
        transfer_line_rows: list[dict[str, Any]] = []
        transfer_line_seq = 1
        transfer_dates = self._sample_dates(n_transfers)

        for i in range(n_transfers):
            transfer_id = f"TR{i + 1:07d}"
            transfer_no = f"TRF-{i + 1:07d}"
            from_index = int(self.rng.integers(0, len(warehouses)))
            to_index = int(self.rng.integers(0, len(warehouses) - 1)) if len(warehouses) > 1 else from_index
            if len(warehouses) > 1 and to_index >= from_index:
                to_index += 1
            transfer_header_rows.append(
                {
                    "transfer_id": transfer_id,
                    "transfer_no": transfer_no,
                    "from_warehouse_id": warehouses.iloc[from_index]["warehouse_id"],
                    "to_warehouse_id": warehouses.iloc[to_index]["warehouse_id"],
                    "posting_date": pd.Timestamp(transfer_dates[i]).date(),
                    "status": "posted",
                }
            )
            line_count = int(self.rng.integers(1, 4))
            product_indices = self.rng.choice(len(products), size=line_count, p=product_weights)
            for line_no, pidx in enumerate(product_indices, start=1):
                transfer_line_rows.append(
                    {
                        "transfer_line_id": f"TRL{transfer_line_seq:09d}",
                        "transfer_id": transfer_id,
                        "line_no": line_no * 10000,
                        "product_id": products.iloc[int(pidx)]["product_id"],
                        "quantity": max(1, int(round(self.rng.lognormal(mean=2.5, sigma=0.55)))),
                    }
                )
                transfer_line_seq += 1

        warehouse_transfer_header = pd.DataFrame(transfer_header_rows)
        warehouse_transfer_line = pd.DataFrame(transfer_line_rows)

        ledger_rows: list[dict[str, Any]] = []
        value_rows: list[dict[str, Any]] = []
        entry_no = 1
        value_no = 1

        def add_ledger(
            *,
            product_id: str,
            warehouse_id: str,
            posting_date: Any,
            entry_type: str,
            quantity: float,
            document_type: str,
            document_no: str,
            document_line_no: int,
            source_entity_type: str,
            source_entity_id: str,
            transfer_pair_id: str | None = None,
            cost_amount_actual: float = 0.0,
            sales_amount_actual: float = 0.0,
            discount_amount: float = 0.0,
        ) -> None:
            nonlocal entry_no, value_no
            ledger_id = f"ILE{entry_no:010d}"
            ledger_rows.append(
                {
                    "inventory_ledger_entry_id": ledger_id,
                    "entry_no": entry_no,
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "posting_date": pd.Timestamp(posting_date).date(),
                    "entry_type": entry_type,
                    "quantity": float(quantity),
                    "remaining_quantity": float(quantity) if quantity > 0 else 0.0,
                    "document_type": document_type,
                    "document_no": document_no,
                    "document_line_no": int(document_line_no),
                    "source_entity_type": source_entity_type,
                    "source_entity_id": source_entity_id,
                    "transfer_pair_id": transfer_pair_id,
                }
            )
            value_rows.append(
                {
                    "value_entry_id": f"VE{value_no:010d}",
                    "value_entry_no": value_no,
                    "inventory_ledger_entry_id": ledger_id,
                    "posting_date": pd.Timestamp(posting_date).date(),
                    "entry_type": entry_type,
                    "cost_amount_actual": round(float(cost_amount_actual), 2),
                    "sales_amount_actual": round(float(sales_amount_actual), 2),
                    "discount_amount": round(float(discount_amount), 2),
                    "document_type": document_type,
                    "document_no": document_no,
                    "document_line_no": int(document_line_no),
                }
            )
            entry_no += 1
            value_no += 1

        low_stock_products = set(
            self.rng.choice(products["product_id"].to_numpy(), size=max(1, int(len(products) * 0.05)), replace=False)
        )
        remaining_products = [p for p in products["product_id"].to_list() if p not in low_stock_products]
        excess_products = set(
            self.rng.choice(
                np.asarray(remaining_products),
                size=max(1, int(len(products) * 0.08)),
                replace=False,
            )
        )

        for _, product_row in products.iterrows():
            product_id = product_row["product_id"]
            unit_cost = float(product_row["standard_unit_cost"])
            for _, warehouse_row in warehouses.iterrows():
                if product_id in low_stock_products:
                    quantity = int(self.rng.integers(0, 8))
                else:
                    quantity = max(5, int(round(self.rng.lognormal(mean=4.0, sigma=0.6))))
                    if product_id in excess_products:
                        quantity *= int(self.rng.integers(4, 8))
                if quantity <= 0:
                    continue
                add_ledger(
                    product_id=product_id,
                    warehouse_id=warehouse_row["warehouse_id"],
                    posting_date=self.start_date,
                    entry_type="positive_adjustment",
                    quantity=quantity,
                    document_type="opening_balance",
                    document_no="OPENING",
                    document_line_no=0,
                    source_entity_type="opening_balance",
                    source_entity_id=f"{product_id}:{warehouse_row['warehouse_id']}",
                    cost_amount_actual=quantity * unit_cost,
                )

        receipt_header_lookup = purchase_receipt_header.set_index("purchase_receipt_id")
        for _, line in purchase_receipt_line.iterrows():
            header = receipt_header_lookup.loc[line["purchase_receipt_id"]]
            add_ledger(
                product_id=line["product_id"],
                warehouse_id=header["warehouse_id"],
                posting_date=header["posting_date"],
                entry_type="purchase_receipt",
                quantity=float(line["quantity"]),
                document_type="purchase_receipt",
                document_no=header["receipt_no"],
                document_line_no=int(line["line_no"]),
                source_entity_type="purchase_receipt_line",
                source_entity_id=line["purchase_receipt_line_id"],
                cost_amount_actual=float(line["quantity"]) * float(line["unit_cost"]),
            )

        invoice_header_lookup = sales["sales_invoice_header"].set_index("sales_invoice_id")
        for _, line in sales["sales_invoice_line"].iterrows():
            header = invoice_header_lookup.loc[line["sales_invoice_id"]]
            quantity = float(line["quantity"])
            unit_cost = float(product_lookup.loc[line["product_id"], "standard_unit_cost"])
            add_ledger(
                product_id=line["product_id"],
                warehouse_id=line["warehouse_id"],
                posting_date=header["posting_date"],
                entry_type="sale",
                quantity=-quantity,
                document_type="sales_invoice",
                document_no=header["invoice_no"],
                document_line_no=int(line["line_no"]),
                source_entity_type="sales_invoice_line",
                source_entity_id=line["sales_invoice_line_id"],
                cost_amount_actual=quantity * unit_cost,
                sales_amount_actual=float(line["net_line_amount"]),
                discount_amount=float(line["discount_amount"]),
            )

        if not sales["sales_credit_memo_line"].empty:
            credit_header_lookup = sales["sales_credit_memo_header"].set_index("sales_credit_memo_id")
            for _, line in sales["sales_credit_memo_line"].iterrows():
                header = credit_header_lookup.loc[line["sales_credit_memo_id"]]
                quantity = float(line["return_quantity"])
                physical_quantity = quantity if line["disposition"] == "restock" else 0.0
                unit_cost = float(product_lookup.loc[line["product_id"], "standard_unit_cost"])
                add_ledger(
                    product_id=line["product_id"],
                    warehouse_id=line["warehouse_id"],
                    posting_date=header["posting_date"],
                    entry_type="sales_return",
                    quantity=physical_quantity,
                    document_type="sales_credit_memo",
                    document_no=header["credit_memo_no"],
                    document_line_no=int(line["line_no"]),
                    source_entity_type="sales_credit_memo_line",
                    source_entity_id=line["sales_credit_memo_line_id"],
                    cost_amount_actual=-(quantity * unit_cost),
                    sales_amount_actual=-float(line["net_credit_amount"]),
                    discount_amount=-float(line["discount_amount"]),
                )

        transfer_header_lookup = warehouse_transfer_header.set_index("transfer_id")
        for _, line in warehouse_transfer_line.iterrows():
            header = transfer_header_lookup.loc[line["transfer_id"]]
            unit_cost = float(product_lookup.loc[line["product_id"], "standard_unit_cost"])
            pair_id = f"PAIR-{line['transfer_line_id']}"
            qty = float(line["quantity"])
            add_ledger(
                product_id=line["product_id"],
                warehouse_id=header["from_warehouse_id"],
                posting_date=header["posting_date"],
                entry_type="transfer_out",
                quantity=-qty,
                document_type="warehouse_transfer",
                document_no=header["transfer_no"],
                document_line_no=int(line["line_no"]),
                source_entity_type="warehouse_transfer_line",
                source_entity_id=line["transfer_line_id"],
                transfer_pair_id=pair_id,
                cost_amount_actual=-(qty * unit_cost),
            )
            add_ledger(
                product_id=line["product_id"],
                warehouse_id=header["to_warehouse_id"],
                posting_date=header["posting_date"],
                entry_type="transfer_in",
                quantity=qty,
                document_type="warehouse_transfer",
                document_no=header["transfer_no"],
                document_line_no=int(line["line_no"]),
                source_entity_type="warehouse_transfer_line",
                source_entity_id=line["transfer_line_id"],
                transfer_pair_id=pair_id,
                cost_amount_actual=qty * unit_cost,
            )

        provisional_ledger = pd.DataFrame(ledger_rows)
        provisional_on_hand = (
            provisional_ledger.groupby(["product_id", "warehouse_id"], as_index=False)["quantity"]
            .sum()
            .rename(columns={"quantity": "on_hand_quantity"})
        )
        provisional_reserved = (
            sales["sales_order_line"]
            .groupby(["product_id", "warehouse_id"], as_index=False)["outstanding_quantity"]
            .sum()
            .rename(columns={"outstanding_quantity": "reserved_quantity"})
        )
        risk_view = provisional_on_hand.merge(
            provisional_reserved,
            on=["product_id", "warehouse_id"],
            how="outer",
        ).fillna(0.0)
        risk_view["available_quantity"] = (
            risk_view["on_hand_quantity"] - risk_view["reserved_quantity"]
        )

        if not bool((risk_view["available_quantity"] <= 0).any()):
            candidates = risk_view[risk_view["reserved_quantity"] > 0].copy()
            if not candidates.empty:
                candidate = candidates.sort_values(
                    ["reserved_quantity", "on_hand_quantity"],
                    ascending=[False, True],
                ).iloc[0]
                adjustment_qty = -(
                    float(candidate["on_hand_quantity"])
                    - float(candidate["reserved_quantity"])
                    + 1.0
                )
                if adjustment_qty < 0:
                    product_id = str(candidate["product_id"])
                    unit_cost = float(product_lookup.loc[product_id, "standard_unit_cost"])
                    add_ledger(
                        product_id=product_id,
                        warehouse_id=str(candidate["warehouse_id"]),
                        posting_date=self.end_date,
                        entry_type="negative_adjustment",
                        quantity=adjustment_qty,
                        document_type="inventory_adjustment",
                        document_no="STOCKOUT-SCENARIO",
                        document_line_no=0,
                        source_entity_type="synthetic_scenario",
                        source_entity_id="stockout-risk-calibration",
                        cost_amount_actual=adjustment_qty * unit_cost,
                    )

        inventory_ledger_entry = pd.DataFrame(ledger_rows)
        value_entry = pd.DataFrame(value_rows)

        on_hand = (
            inventory_ledger_entry.groupby(["product_id", "warehouse_id"], as_index=False)["quantity"]
            .sum()
            .rename(columns={"quantity": "on_hand_quantity"})
        )
        reserved = (
            sales["sales_order_line"]
            .groupby(["product_id", "warehouse_id"], as_index=False)["outstanding_quantity"]
            .sum()
            .rename(columns={"outstanding_quantity": "reserved_quantity"})
        )
        product_warehouse_grid = pd.MultiIndex.from_product(
            [
                products["product_id"].to_list(),
                warehouses["warehouse_id"].to_list(),
            ],
            names=["product_id", "warehouse_id"],
        ).to_frame(index=False)
        inventory_balance = (
            product_warehouse_grid
            .merge(on_hand, on=["product_id", "warehouse_id"], how="left")
            .merge(reserved, on=["product_id", "warehouse_id"], how="left")
            .fillna(0.0)
        )
        inventory_balance["on_hand_quantity"] = inventory_balance["on_hand_quantity"].round(4)
        inventory_balance["reserved_quantity"] = inventory_balance["reserved_quantity"].round(4)
        inventory_balance["available_quantity"] = (
            inventory_balance["on_hand_quantity"] - inventory_balance["reserved_quantity"]
        ).round(4)
        inventory_balance["snapshot_date"] = self.end_date.date()
        inventory_balance.insert(
            0,
            "inventory_balance_id",
            [
                f"IB-{product_id}-{warehouse_id}"
                for product_id, warehouse_id in zip(
                    inventory_balance["product_id"],
                    inventory_balance["warehouse_id"],
                )
            ],
        )
        inventory_balance = inventory_balance[
            [
                "inventory_balance_id",
                "product_id",
                "warehouse_id",
                "snapshot_date",
                "on_hand_quantity",
                "reserved_quantity",
                "available_quantity",
            ]
        ]

        return {
            "purchase_receipt_header": purchase_receipt_header,
            "purchase_receipt_line": purchase_receipt_line,
            "warehouse_transfer_header": warehouse_transfer_header,
            "warehouse_transfer_line": warehouse_transfer_line,
            "inventory_ledger_entry": inventory_ledger_entry,
            "value_entry": value_entry,
            "inventory_balance": inventory_balance,
        }


def dataset_fingerprint(dataset: dict[str, pd.DataFrame]) -> str:
    digest = hashlib.sha256()
    for name in ENTITY_ORDER:
        frame = dataset[name].copy()
        digest.update(name.encode("utf-8"))
        digest.update("|".join(frame.columns).encode("utf-8"))
        hashed = pd.util.hash_pandas_object(frame, index=False, categorize=True).to_numpy()
        digest.update(hashed.tobytes())
    return digest.hexdigest()


def export_dataset(
    dataset: dict[str, pd.DataFrame],
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    for name in ENTITY_ORDER:
        dataset[name].to_csv(output / f"{name}.csv", index=False, date_format="%Y-%m-%d")

    manifest = {
        "schema_version": 1,
        "entities": {
            name: {
                "rows": int(len(dataset[name])),
                "columns": list(dataset[name].columns),
            }
            for name in ENTITY_ORDER
        },
        "fingerprint": dataset_fingerprint(dataset),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if validation is not None:
        report = dict(validation)
        report["dataset_fingerprint"] = manifest["fingerprint"]
        (output / "validation.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
