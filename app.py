
import os
from io import BytesIO
import pandas as pd
from flask import Flask, render_template, request, send_file, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-demo-secret")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED = {".csv", ".xlsx"}

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    preview = None
    stats = None

    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            error = "Please select a CSV or Excel file."
        elif os.path.splitext(file.filename)[1].lower() not in ALLOWED:
            error = "Only CSV and XLSX files are supported."
        else:
            try:
                raw = file.read()
                df = (pd.read_csv(BytesIO(raw))
                      if file.filename.lower().endswith(".csv")
                      else pd.read_excel(BytesIO(raw)))

                original_rows = len(df)
                original_missing = int(df.isna().sum().sum())
                remove_duplicates = request.form.get("duplicates") == "yes"
                trim_spaces = request.form.get("spaces") == "yes"
                fill_missing = request.form.get("missing") == "yes"

                if trim_spaces:
                    for col in df.select_dtypes(include=["object", "string"]):
                        df[col] = df[col].map(
                            lambda x: x.strip() if isinstance(x, str) else x
                        )

                if remove_duplicates:
                    df = df.drop_duplicates()

                if fill_missing:
                    for col in df.columns:
                        if pd.api.types.is_numeric_dtype(df[col]):
                            if df[col].isna().any():
                                df[col] = df[col].fillna(df[col].median())
                        elif df[col].isna().any():
                            df[col] = df[col].fillna("Unknown")

                session["cleaned"] = df.to_json(orient="split", date_format="iso")
                session["format"] = os.path.splitext(file.filename)[1].lower()

                stats = {
                    "rows_before": original_rows,
                    "rows_after": len(df),
                    "duplicates_removed": original_rows - len(df)
                        if remove_duplicates else 0,
                    "missing_before": original_missing,
                    "missing_after": int(df.isna().sum().sum()),
                    "columns": len(df.columns)
                }
                preview = df.head(100).fillna("").to_dict(orient="records")
                columns = df.columns.tolist()
                return render_template(
                    "index.html", error=error, preview=preview,
                    columns=columns, stats=stats
                )
            except Exception:
                error = "Could not read this file. Check that it is a valid CSV or Excel file."

    return render_template(
        "index.html", error=error, preview=preview, columns=[],
        stats=stats
    )

@app.route("/download")
def download():
    data = session.get("cleaned")
    fmt = session.get("format", ".csv")
    if not data:
        return "Please upload and clean a file first.", 400

    df = pd.read_json(BytesIO(data.encode()), orient="split")
    output = BytesIO()

    if fmt == ".xlsx":
        df.to_excel(output, index=False, engine="openpyxl")
        filename = "cleaned_data.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        df.to_csv(output, index=False)
        filename = "cleaned_data.csv"
        mimetype = "text/csv"

    output.seek(0)
    return send_file(
        output, as_attachment=True, download_name=filename,
        mimetype=mimetype
    )

if __name__ == "__main__":
    app.run(debug=True)
