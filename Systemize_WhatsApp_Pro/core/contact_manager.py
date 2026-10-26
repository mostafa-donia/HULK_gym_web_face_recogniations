import os
import re
import csv
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd


class Contact:
    def __init__(
        self,
        phone: str,
        name: str = "",
        category: str = "عام",
        notes: str = "",
        custom_data: Optional[Dict[str, Any]] = None,
        selected: bool = True
    ):
        self.raw_phone = str(phone).strip()
        self.phone = self.normalize_phone(self.raw_phone)
        self.name = str(name).strip() or "عميلنا العزيز"
        self.category = str(category).strip() or "عام"
        self.notes = str(notes).strip()
        self.custom_data = custom_data or {}
        self.selected = selected
        self.status = "معلق"  # معلق, جاري, تم الإرسال, فشل
        self.sent_time = None
        self.error_message = ""

    @staticmethod
    def normalize_phone(phone_str: str) -> str:
        """
        Cleans and formats phone numbers:
        - Strips whitespace, dashes, parentheses.
        - Formats Egyptian numbers (010, 011, 012, 015) to 201XXXXXXXXX.
        - Preserves existing country code if present.
        """
        clean = re.sub(r"[^\d+]", "", str(phone_str))
        if clean.startswith("+"):
            clean = clean[1:]

        # Egyptian phone number normalization
        if re.match(r"^01[0125]\d{8}$", clean):
            clean = "2" + clean
        elif re.match(r"^1[0125]\d{8}$", clean):
            clean = "20" + clean

        return clean

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phone": self.phone,
            "raw_phone": self.raw_phone,
            "category": self.category,
            "notes": self.notes,
            "status": self.status,
            "sent_time": self.sent_time,
            "error_message": self.error_message,
            **self.custom_data
        }


class ContactManager:
    def __init__(self):
        self.contacts: List[Contact] = []
        self.categories: List[str] = ["الكل"]

    def clear(self):
        self.contacts.clear()
        self.categories = ["الكل"]

    def add_contact(self, phone: str, name: str = "", category: str = "عام", notes: str = "", custom_data: dict = None) -> Contact:
        c = Contact(phone=phone, name=name, category=category, notes=notes, custom_data=custom_data)
        self.contacts.append(c)
        if c.category and c.category not in self.categories:
            self.categories.append(c.category)
        return c

    def load_from_file(self, file_path: str) -> Tuple[int, List[str]]:
        """
        Loads contacts from Excel (.xlsx, .xls) or CSV / Google Contacts.
        Returns: (count_imported, list_of_detected_categories)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"الملف غير موجود: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        elif ext == ".csv":
            df = self._read_csv_smart(file_path)
        else:
            raise ValueError("صيغة الملف غير مدعومة. يرجى اختيار ملف Excel (.xlsx/.xls) أو CSV.")

        return self._import_dataframe(df)

    def _read_csv_smart(self, file_path: str) -> pd.DataFrame:
        """Reads CSV detecting encoding and delimiter automatically."""
        encodings = ["utf-8-sig", "utf-8", "cp1256", "iso-8859-1"]
        for enc in encodings:
            try:
                # Sniff delimiter
                with open(file_path, "r", encoding=enc, errors="ignore") as f:
                    sample = f.read(4096)
                    try:
                        dialect = csv.Sniffer().sniff(sample)
                        sep = dialect.delimiter
                    except Exception:
                        sep = "," if "," in sample else (";" if ";" in sample else "\t")

                df = pd.read_csv(file_path, encoding=enc, sep=sep)
                if not df.empty:
                    return df
            except Exception:
                continue

        # Fallback
        return pd.read_csv(file_path, encoding="utf-8", errors="replace")

    def _import_dataframe(self, df: pd.DataFrame) -> Tuple[int, List[str]]:
        if df.empty:
            return 0, []

        cols = [str(c).strip() for c in df.columns]
        cols_lower = [c.lower() for c in cols]

        # Column identification mapping
        phone_col = None
        name_col = None
        cat_col = None
        notes_col = None

        # 1. Match Phone Column
        phone_patterns = ["phone 1 - value", "phone", "mobile", "whatsapp", "tel", "موبايل", "هاتف", "رقم", "جوال"]
        for pat in phone_patterns:
            for idx, c in enumerate(cols_lower):
                if pat in c:
                    phone_col = cols[idx]
                    break
            if phone_col:
                break

        if not phone_col:
            # Fallback: check columns that contain mostly numeric strings
            for col in cols:
                sample_vals = df[col].dropna().astype(str).head(10)
                if any(re.search(r"\d{7,}", s) for s in sample_vals):
                    phone_col = col
                    break

        if not phone_col:
            raise ValueError("لم يتم العثور على عمود الهاتف / الموبايل في الملف. تأكد من وجود عمود باسم (الهاتف أو Phone).")

        # 2. Match Name Column
        name_patterns = ["name", "full_name", "given name", "اسم", "الاسم", "العميل", "الكابتن", "صاحب الرقم"]
        for pat in name_patterns:
            for idx, c in enumerate(cols_lower):
                if pat in c and cols[idx] != phone_col:
                    name_col = cols[idx]
                    break
            if name_col:
                break

        # Check Google Contacts First + Last name combination
        first_name_col = None
        last_name_col = None
        if not name_col:
            for idx, c in enumerate(cols_lower):
                if "given name" in c or "first name" in c:
                    first_name_col = cols[idx]
                if "family name" in c or "last name" in c:
                    last_name_col = cols[idx]

        # 3. Match Category / Group Column
        cat_patterns = ["group membership", "category", "group", "tag", "تصنيف", "الفئة", "المجموعة", "نوع", "الحالة"]
        for pat in cat_patterns:
            for idx, c in enumerate(cols_lower):
                if pat in c and cols[idx] not in [phone_col, name_col]:
                    cat_col = cols[idx]
                    break
            if cat_col:
                break

        # 4. Match Notes Column
        notes_patterns = ["notes", "note", "ملاحظات", "تفاصيل", "الوصف"]
        for pat in notes_patterns:
            for idx, c in enumerate(cols_lower):
                if pat in c and cols[idx] not in [phone_col, name_col, cat_col]:
                    notes_col = cols[idx]
                    break
            if notes_col:
                break

        imported_count = 0
        seen_phones = set()

        for _, row in df.iterrows():
            raw_phone = str(row.get(phone_col, "")).strip()
            if not raw_phone or raw_phone.lower() in ["nan", "none", "null"]:
                continue

            # Resolve name
            name_val = ""
            if name_col and pd.notna(row.get(name_col)):
                name_val = str(row.get(name_col)).strip()
            elif first_name_col:
                first = str(row.get(first_name_col, "")).strip() if pd.notna(row.get(first_name_col)) else ""
                last = str(row.get(last_name_col, "")).strip() if last_name_col and pd.notna(row.get(last_name_col)) else ""
                name_val = f"{first} {last}".strip()

            if name_val.lower() in ["nan", "none", "null"]:
                name_val = ""

            # Resolve category
            cat_val = "عام"
            if cat_col and pd.notna(row.get(cat_col)):
                raw_cat = str(row.get(cat_col)).strip()
                # Clean Google contacts tags like "* myContacts ::: Group Name"
                if ":::" in raw_cat:
                    raw_cat = raw_cat.split(":::")[-1].strip()
                if raw_cat and raw_cat.lower() not in ["nan", "none", "null"]:
                    cat_val = raw_cat

            # Resolve notes
            notes_val = ""
            if notes_col and pd.notna(row.get(notes_col)):
                notes_val = str(row.get(notes_col)).strip()
                if notes_val.lower() in ["nan", "none", "null"]:
                    notes_val = ""

            # Collect other columns as custom data
            custom_data = {}
            for c in cols:
                if c not in [phone_col, name_col, cat_col, notes_col, first_name_col, last_name_col]:
                    val = row.get(c)
                    if pd.notna(val):
                        custom_data[str(c)] = str(val).strip()

            contact = Contact(
                phone=raw_phone,
                name=name_val or "عميلنا العزيز",
                category=cat_val,
                notes=notes_val,
                custom_data=custom_data,
                selected=True
            )

            # Deduplicate by normalized phone
            if contact.phone and contact.phone not in seen_phones:
                seen_phones.add(contact.phone)
                self.contacts.append(contact)
                imported_count += 1
                if contact.category not in self.categories:
                    self.categories.append(contact.category)

        return imported_count, self.get_categories()

    def get_categories(self) -> List[str]:
        cats = ["الكل"]
        for c in self.contacts:
            if c.category and c.category not in cats:
                cats.append(c.category)
        return cats

    def filter_contacts(self, category: str = "الكل", search_query: str = "") -> List[Contact]:
        filtered = self.contacts
        if category and category != "الكل":
            filtered = [c for c in filtered if c.category == category]

        if search_query:
            query = search_query.strip().lower()
            filtered = [
                c for c in filtered
                if query in c.name.lower() or query in c.phone.lower() or query in c.category.lower() or query in c.notes.lower()
            ]

        return filtered

    def get_selected_contacts(self, category: str = "الكل") -> List[Contact]:
        return [c for c in self.filter_contacts(category=category) if c.selected]

    def select_all(self, selected: bool = True, category: str = "الكل"):
        for c in self.filter_contacts(category=category):
            c.selected = selected

    def export_to_excel(self, file_path: str, contacts_to_export: Optional[List[Contact]] = None):
        target = contacts_to_export if contacts_to_export is not None else self.contacts
        data = [c.to_dict() for c in target]
        df = pd.DataFrame(data)
        df.to_excel(file_path, index=False)
