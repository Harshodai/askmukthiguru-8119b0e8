import sys

import PyPDF2


def extract(pdf_path):
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for i in range(min(15, len(reader.pages))):
            text += reader.pages[i].extract_text() + "\n"
        print(text)


if __name__ == "__main__":
    extract(sys.argv[1])
