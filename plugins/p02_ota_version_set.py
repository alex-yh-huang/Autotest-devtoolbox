from typing import Any

import pymysql
from pymysql import MySQLError
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.plugin_base import PluginBase


DB_HOST = "192.168.50.66"
DB_PORT = 3306
DB_USER = ""
DB_PASSWORD = ""
DB_NAME = ""

TABLE_NAME = ""


class OtaVersionEditDialog(QDialog):
    def __init__(
        self,
        columns: list[str],
        row_data: dict[str, Any] | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.inputs: dict[str, QLineEdit] = {}

        self.setWindowTitle("OTA Version Set")
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        row_data = row_data or {}

        for col in columns:
            edit = QLineEdit()
            value = row_data.get(col)
            edit.setText("" if value is None else str(value))
            edit.setMinimumHeight(30)
            self.inputs[col] = edit
            form.addRow(QLabel(col), edit)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def get_values(self) -> dict[str, str | None]:
        values = {}

        for col, edit in self.inputs.items():
            text = edit.text().strip()
            values[col] = text if text else None

        return values


class OtaVersionSetPlugin(PluginBase):
    PLUGIN_NAME = "OTA Version Set"
    PLUGIN_ICON = "🚗"
    PLUGIN_DESC = "Manage MySQL ota_version table"
    PLUGIN_ORDER = 3

    def setup_ui(self):
        self.conn = None
        self.table_columns: list[dict[str, Any]] = []
        self.primary_key_col: str | None = None
        self.editable_columns: list[str] = []

        self._setup_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        title = QLabel("OTA Version Set")
        title.setObjectName("PageTitle")
        main_layout.addWidget(title)

        main_layout.addWidget(self._create_action_group())

        self.lbl_status = QLabel("Connecting...")
        self.lbl_status.setObjectName("StatusLabel")
        main_layout.addWidget(self.lbl_status)

        self.table = QTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)

        main_layout.addWidget(self.table, 1)


    def _setup_style(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #e8e8e8;
                font-size: 13px;
            }

            QLabel {
                color: #e8e8e8;
            }

            QLabel#PageTitle {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 4px;
            }

            QLabel#StatusLabel {
                color: #b5b5b5;
                font-size: 13px;
                padding: 4px 0;
            }

            QGroupBox {
                color: #ffffff;
                background-color: #1e1e1e;
                font-size: 14px;
                font-weight: 600;
                border: 1px solid #555555;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px 12px 12px 12px;
            }

            QGroupBox::title {
                color: #ffffff;
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }

            QLineEdit {
                color: #ffffff;
                background-color: #2b2b2b;
                min-height: 32px;
                padding: 4px 8px;
                border: 1px solid #666666;
                border-radius: 5px;
                font-size: 13px;
            }

            QLineEdit::placeholder {
                color: #9a9a9a;
            }

            QPushButton {
                color: #ffffff;
                background-color: #2f2f2f;
                min-height: 32px;
                min-width: 100px;
                padding: 4px 12px;
                border: 1px solid #666666;
                border-radius: 5px;
                font-size: 13px;
            }

            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #6a9cff;
            }

            QPushButton:pressed {
                background-color: #4a4a4a;
            }

            QTableWidget {
                color: #e8e8e8;
                background-color: #1f1f1f;
                alternate-background-color: #262626;
                gridline-color: #444444;
                border: 1px solid #555555;
                border-radius: 6px;
                font-size: 13px;
                selection-background-color: #315a8c;
                selection-color: #ffffff;
            }

            QHeaderView::section {
                color: #ffffff;
                background-color: #333333;
                font-weight: 600;
                padding: 6px;
                border: 1px solid #555555;
            }

            QTableWidget::item {
                padding: 5px;
            }
        """)

    def _create_action_group(self) -> QGroupBox:
        group = QGroupBox("Actions")
        layout = QHBoxLayout(group)
        layout.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search keyword...")
        self.txt_search.returnPressed.connect(self._load_rows)

        btn_connect = QPushButton("Connect")
        btn_connect.clicked.connect(self._connect_db)

        btn_search = QPushButton("Search")
        btn_search.clicked.connect(self._load_rows)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh)

        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._add_row)

        btn_modify = QPushButton("Modify Selected")
        btn_modify.clicked.connect(self._modify_selected_row)

        layout.addWidget(QLabel("Keyword:"))
        layout.addWidget(self.txt_search, 1)
        layout.addWidget(btn_connect)
        layout.addWidget(btn_search)
        layout.addWidget(btn_refresh)
        layout.addWidget(btn_add)
        layout.addWidget(btn_modify)

        return group

    def _connect_db(self):
        try:
            self.lbl_status.setText("Connecting to MySQL...")
            self.lbl_status.setStyleSheet("color: #ffcc66;")

            self.conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10,
            )

            self._load_schema()
            self._load_rows()

            self.lbl_status.setText(
                f"Connected to MySQL / DB: {DB_NAME} / Table: {TABLE_NAME}"
            )
            self.lbl_status.setStyleSheet("color: #4caf50;")

        except MySQLError as e:
            self.conn = None
            self.lbl_status.setText(f"Connect failed: {e}")
            self.lbl_status.setStyleSheet("color: #ff6b6b;")

        except Exception as e:
            self.conn = None
            self.lbl_status.setText(f"Connect failed: {e}")
            self.lbl_status.setStyleSheet("color: #ff6b6b;")


    def _load_schema(self):
        self._ensure_connected()

        sql = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                COLUMN_KEY,
                EXTRA,
                IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """

        with self.conn.cursor() as cursor:
            cursor.execute(sql, (DB_NAME, TABLE_NAME))
            rows = cursor.fetchall()

        if not rows:
            raise RuntimeError(f"Table does not exist: {DB_NAME}.{TABLE_NAME}")

        self.table_columns = rows

        pk_cols = [
            row["COLUMN_NAME"]
            for row in rows
            if row.get("COLUMN_KEY") == "PRI"
        ]

        self.primary_key_col = pk_cols[0] if pk_cols else rows[0]["COLUMN_NAME"]

        excluded = {
            self.primary_key_col,
            "created_at",
            "updated_at",
            "create_time",
            "update_time",
        }

        self.editable_columns = [
            row["COLUMN_NAME"]
            for row in rows
            if row["COLUMN_NAME"] not in excluded
            and "auto_increment" not in str(row.get("EXTRA", "")).lower()
        ]

    def _load_rows(self):
        self._ensure_connected()

        self.table.setSortingEnabled(False)

        columns = [row["COLUMN_NAME"] for row in self.table_columns]
        keyword = self.txt_search.text().strip()

        sql = f"""
            SELECT {", ".join([f"`{col}`" for col in columns])}
            FROM `{TABLE_NAME}`
        """

        params: list[Any] = []

        if keyword:
            where_clause = " OR ".join(
                [f"CAST(`{col}` AS CHAR) LIKE %s" for col in columns]
            )
            sql += f" WHERE {where_clause}"
            params = [f"%{keyword}%"] * len(columns)

        sql += f" ORDER BY `{self.primary_key_col}` DESC"

        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            self.table.setRowHeight(row_idx, 32)

            for col_idx, col in enumerate(columns):
                value = row.get(col)
                item = QTableWidgetItem("" if value is None else str(value))

                if col == self.primary_key_col:
                    item.setData(Qt.ItemDataRole.UserRole, row.get(col))

                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

        self.lbl_status.setText(f"Loaded {len(rows)} rows from {DB_NAME}.{TABLE_NAME}")
        self.lbl_status.setStyleSheet("color: #4caf50;")

    def _refresh(self):
        self._ensure_connected()
        self._load_schema()
        self._load_rows()

    def _add_row(self):
        self._ensure_connected()

        dialog = OtaVersionEditDialog(
            columns=self.editable_columns,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        values = dialog.get_values()

        insert_cols = list(values.keys())
        placeholders = ", ".join(["%s"] * len(insert_cols))

        sql = (
            f"INSERT INTO `{TABLE_NAME}` "
            f"({', '.join([f'`{col}`' for col in insert_cols])}) "
            f"VALUES ({placeholders})"
        )

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, [values[col] for col in insert_cols])

            self.conn.commit()
            self._load_rows()
            self._show_info("Add success", "New OTA version set has been added.")

        except MySQLError as e:
            self.conn.rollback()
            self._show_error("Add failed", str(e))

    def _modify_selected_row(self):
        self._ensure_connected()

        selected = self.table.selectionModel().selectedRows()

        if not selected:
            self._show_warning("No row selected", "Please select one row to modify.")
            return

        selected_row_idx = selected[0].row()
        row_data = self._get_row_data_from_table(selected_row_idx)

        pk_value = row_data.get(self.primary_key_col)

        if pk_value is None:
            self._show_error(
                "Modify failed",
                f"Primary key value is missing: {self.primary_key_col}",
            )
            return

        editable_row_data = {
            col: row_data.get(col)
            for col in self.editable_columns
        }

        dialog = OtaVersionEditDialog(
            columns=self.editable_columns,
            row_data=editable_row_data,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        values = dialog.get_values()
        set_clause = ", ".join([f"`{col}` = %s" for col in values.keys()])

        sql = (
            f"UPDATE `{TABLE_NAME}` "
            f"SET {set_clause} "
            f"WHERE `{self.primary_key_col}` = %s"
        )

        try:
            params = [values[col] for col in values.keys()]
            params.append(pk_value)

            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)

            self.conn.commit()
            self._load_rows()
            self._show_info("Modify success", "Selected OTA version set has been updated.")

        except MySQLError as e:
            self.conn.rollback()
            self._show_error("Modify failed", str(e))

    def _get_row_data_from_table(self, row_idx: int) -> dict[str, Any]:
        data = {}

        for col_idx in range(self.table.columnCount()):
            col_name = self.table.horizontalHeaderItem(col_idx).text()
            item = self.table.item(row_idx, col_idx)
            data[col_name] = item.text() if item else None

        return data

    def _ensure_connected(self):
        if self.conn is None or not self.conn.open:
            raise RuntimeError("Please connect MySQL first.")

    def _show_info(self, title: str, text: str):
        QMessageBox.information(self, title, text)

    def _show_warning(self, title: str, text: str):
        QMessageBox.warning(self, title, text)

    def _show_error(self, title: str, text: str):
        QMessageBox.critical(self, title, text)

    def on_activated(self):
        if self.conn and self.conn.open:
            self._load_rows()

    def on_deactivated(self):
        pass