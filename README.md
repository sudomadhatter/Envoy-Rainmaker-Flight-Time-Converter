# ✈️ Envoy Rainmaker Flight Time Converter

**A 1-click automatic flight log extractor for Envoy Air pilots.**  
Convert your monthly Envoy Rainmaker schedule PDFs into a single file ready to upload into **LogTen Pro**.


No coding required!

---

## 🚀 Easy 3-Step Guide

### Step 1: Put your monthly PDFs in the `new` folder
- Copy your monthly schedule PDF files into the **`new`** folder inside this project.
- *Tip:* Make sure the file names include the month and year (for example: `2024-11.pdf` or `Nov_2024.pdf`).

---

### Step 2: Double-click `go.command`
1. Double-click the file named **`go.command`**.
2. A black Terminal window will open and automatically do all the work!

> [!NOTE]
> **First time opening on Mac?**  
> If Mac displays a security message saying *"go.command cannot be opened because it is from an unidentified developer"*:
> 1. Right-click (or Control-click) **`go.command`**.
> 2. Click **Open** from the menu.
> 3. Click **Open** again when prompted.

---

### Step 3: Get your final LogTen Pro file
When the window finishes, your completed logbook file will be waiting in the **`logten pro format`** folder:
- **`logten_pro_import.csv`**

Your original PDFs will automatically be moved to the **`scraped`** folder for safekeeping!

---

## 📲 How to Upload to LogTen Pro (Mac)

1. Open **LogTen Pro** on your Mac.
2. At the top menu bar, click **File** $\rightarrow$ **Import from File** $\rightarrow$ **Flights...**
3. Select **`logten_pro_import.csv`** from your `logten pro format` folder.
4. Click **Import**.

Your flights, flight numbers, aircraft type, actual Zulu departure/arrival times, and PIC/SIC hours will automatically sync to your iPhone and iPad via iCloud!

---

## ❓ Frequently Asked Questions

#### **Q: Do I need to install Python or code anything?**
No! When you double-click `go.command`, it automatically sets up everything needed in the background.

#### **Q: What if I add more monthly PDFs later?**
Just put the new PDF files in the `new` folder and double-click `go.command` again. It will add the new flights to your master logbook file without creating duplicates.

---

## 📜 License
MIT License - Free to use and share.
