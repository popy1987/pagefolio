"""Flask BS server: static web + REST API."""

from __future__ import annotations

from flask import Flask, jsonify, request, send_file, send_from_directory

from pagefolio.config import COVER_DIR, DB_PATH, HOST, PORT, ROOT, WEB_DIR
from pagefolio.covers import download_cover_for_book
from pagefolio.db import book_to_dict, connect
from pagefolio.sources import fetch_from_url


def create_app() -> Flask:
    index_path = WEB_DIR / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"Missing frontend: {index_path}")

    app = Flask(__name__)

    @app.get("/")
    def index() -> object:
        return send_file(index_path)

    @app.get("/cover/<path:filename>")
    def cover_file(filename: str) -> object:
        return send_from_directory(str(COVER_DIR), filename)

    @app.get("/assets/<path:filename>")
    def asset_file(filename: str) -> object:
        return send_from_directory(str(WEB_DIR / "assets"), filename)

    @app.get("/api/years")
    def api_years() -> object:
        with connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT year FROM reading_months ORDER BY year DESC"
            ).fetchall()
        return jsonify([r["year"] for r in rows])

    @app.get("/api/reading")
    def api_reading() -> object:
        year = request.args.get("year", type=int)
        if year is None:
            return jsonify({"error": "year required"}), 400
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT rm.id AS reading_id, rm.year, rm.month, rm.finished_on,
                       rm.notes AS reading_notes,
                       b.id, b.title, b.subtitle, b.author, b.translator,
                       b.isbn, b.asin, b.cover_url,
                       b.local_cover_path, b.publisher, b.language, b.notes,
                       b.created_at, b.updated_at
                FROM reading_months rm
                JOIN books b ON b.id = rm.book_id
                WHERE rm.year = ?
                ORDER BY rm.month, b.title, rm.id
                """,
                (year,),
            ).fetchall()
        months: dict[int, list[dict]] = {}
        for row in rows:
            item = book_to_dict(row)
            item.update(
                reading_id=row["reading_id"],
                month=row["month"],
                finished_on=row["finished_on"],
                reading_notes=row["reading_notes"],
            )
            months.setdefault(row["month"], []).append(item)
        return jsonify({"year": year, "months": months})

    @app.get("/api/books/<int:book_id>")
    def api_book(book_id: int) -> object:
        with connect() as conn:
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
            if not row:
                return jsonify({"error": "not found"}), 404
            readings = conn.execute(
                """
                SELECT id, year, month, finished_on, notes
                FROM reading_months WHERE book_id = ?
                ORDER BY year DESC, month DESC, id DESC
                """,
                (book_id,),
            ).fetchall()
        data = book_to_dict(row)
        data["readings"] = [dict(r) for r in readings]
        return jsonify(data)

    @app.delete("/api/books/<int:book_id>")
    def api_delete_book(book_id: int) -> object:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, local_cover_path FROM books WHERE id = ?", (book_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "书目不存在"}), 404
            local_cover = row["local_cover_path"]
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()

        if local_cover:
            cover_path = ROOT / local_cover
            if cover_path.is_file():
                cover_path.unlink(missing_ok=True)

        return jsonify({"ok": True})

    @app.post("/api/books")
    def api_create_book() -> object:
        payload = request.get_json(silent=True) or {}
        url = (payload.get("url") or "").strip()
        year = payload.get("year")
        month = payload.get("month")

        if not url:
            return jsonify({"error": "请提供书籍链接"}), 400
        if year is None or month is None:
            return jsonify({"error": "请填写年度和月份"}), 400
        if not (1 <= int(month) <= 12):
            return jsonify({"error": "月份需在 1–12 之间"}), 400

        try:
            info = fetch_from_url(url)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"链接解析失败：{exc}"}), 502

        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO books (
                  title, subtitle, author, translator,
                  isbn, asin, cover_url, publisher
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    info["title"],
                    info.get("subtitle"),
                    info.get("author"),
                    info.get("translator"),
                    info.get("isbn"),
                    info.get("asin"),
                    info.get("cover_url"),
                    info.get("publisher"),
                ),
            )
            book_id = cur.lastrowid
            conn.execute(
                "INSERT INTO reading_months (book_id, year, month) VALUES (?, ?, ?)",
                (book_id, int(year), int(month)),
            )
            conn.commit()

        local_path = None
        if info.get("cover_url"):
            try:
                local_path = download_cover_for_book(info["cover_url"], book_id)
                with connect() as conn:
                    conn.execute(
                        "UPDATE books SET local_cover_path = ? WHERE id = ?",
                        (local_path, book_id),
                    )
                    conn.commit()
            except ValueError:
                pass

        with connect() as conn:
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()

        return jsonify({"ok": True, "book": book_to_dict(row)}), 201

    def _apply_match(book_id: int, info: dict) -> dict:
        local_path = None
        if info.get("cover_url"):
            local_path = download_cover_for_book(info["cover_url"], book_id)
        with connect() as conn:
            conn.execute(
                """
                UPDATE books SET
                  title = ?, subtitle = ?, author = ?, translator = ?,
                  isbn = COALESCE(?, isbn),
                  asin = COALESCE(?, asin),
                  cover_url = ?,
                  local_cover_path = COALESCE(?, local_cover_path),
                  publisher = COALESCE(?, publisher),
                  updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    info["title"],
                    info.get("subtitle"),
                    info.get("author"),
                    info.get("translator"),
                    info.get("isbn"),
                    info.get("asin"),
                    info.get("cover_url"),
                    local_path,
                    info.get("publisher"),
                    book_id,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return book_to_dict(row)

    def _verify_source(book_id: int, url: str) -> object:
        if not url:
            return jsonify({"error": "请提供书籍链接"}), 400
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone():
                return jsonify({"error": "书目不存在"}), 404
        try:
            return jsonify(fetch_from_url(url))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"抓取失败：{exc}"}), 502

    def _match_source(book_id: int, url: str) -> object:
        if not url:
            return jsonify({"error": "请提供书籍链接"}), 400
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone():
                return jsonify({"error": "书目不存在"}), 404
        try:
            info = fetch_from_url(url)
            book = _apply_match(book_id, info)
            return jsonify({"ok": True, "book": book})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"更新失败：{exc}"}), 502

    @app.post("/api/books/<int:book_id>/verify-source")
    def api_verify_source(book_id: int) -> object:
        url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
        return _verify_source(book_id, url)

    @app.post("/api/books/<int:book_id>/match-source")
    def api_match_source(book_id: int) -> object:
        url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
        return _match_source(book_id, url)

    @app.post("/api/books/<int:book_id>/verify-douban")
    def api_verify_douban(book_id: int) -> object:
        url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
        return _verify_source(book_id, url)

    @app.post("/api/books/<int:book_id>/match-douban")
    def api_match_douban(book_id: int) -> object:
        url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
        return _match_source(book_id, url)

    return app


def run_server() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Missing {DB_PATH}; run: python run.py init")
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Pagefolio → http://{HOST}:{PORT}")
    create_app().run(host=HOST, port=PORT, debug=False)
