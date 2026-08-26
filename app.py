import os
import re
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import sqlite3

app = Flask(__name__)
app.secret_key = 'makkah_lighting_secret_key_2026'

DB_NAME = 'lighting_database.db'
UPLOAD_FOLDER = 'uploads'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # تحسين أداء قواعد البيانات للإدخال السريع للكميات الكبيرة
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # تحديث الجدول ليتطابق مع الأعمدة الجديدة في الصورة
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS poles (
            pole_ID TEXT PRIMARY KEY,
            Latitude TEXT,
            Longitude TEXT,
            Pole_Name TEXT,
            QR_image TEXT,
            Pole_Height TEXT,
            Lamp_Type TEXT,
            Pole_Status TEXT,
            Lamp_Status TEXT,
            Door_Status TEXT,
            Feeder TEXT,
            Panel_No TEXT,
            Base_Depth TEXT,
            Flange_Size TEXT,
            technician_notes TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    cursor.execute('SELECT COUNT(*) FROM admin_config')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO admin_config (username, password) VALUES (?, ?)', ('admin', 'admin123'))

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS technicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    if 'admin_logged' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM admin_config WHERE username = ? AND password = ?', (u, p))
        admin = cursor.fetchone()
        conn.close()
        if admin:
            session['admin_logged'] = True
            return redirect(url_for('dashboard'))
        flash('بيانات الدخول غير صحيحة', 'danger')
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'admin_logged' not in session:
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_admin':
            new_user = request.form.get('admin_username')
            new_pass = request.form.get('admin_password')
            if new_user and new_pass:
                cursor.execute('UPDATE admin_config SET username = ?, password = ? WHERE id = 1', (new_user, new_pass))
                conn.commit()
                flash('تم تحديث بيانات دخول الإدارة بنجاح', 'success')

        elif action == 'add_tech':
            t_user = request.form.get('tech_username')
            t_pass = request.form.get('tech_password')
            t_name = request.form.get('tech_name')
            try:
                cursor.execute('INSERT INTO technicians (username, password, full_name) VALUES (?, ?, ?)', (t_user, t_pass, t_name))
                conn.commit()
                flash('تم إضافة حساب الفني بنجاح', 'success')
            except:
                flash('اسم المستخدم للفني موجود مسبقاً', 'danger')

        elif action == 'delete_tech':
            t_id = request.form.get('tech_id')
            cursor.execute('DELETE FROM technicians WHERE id = ?', (t_id,))
            conn.commit()
            flash('تم حذف حساب الفني بنجاح', 'info')

        # 1. خيار استبدال البيانات بالكامل (يدعم 20 ألف صف وأكثر بسرعة فائقة)
        elif action == 'upload_excel':
            file = request.files.get('excel_file')
            if file and file.filename.endswith(('.xlsx', '.xls')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                try:
                    # قراءة الإكسل دفعة واحدة باستخدام pandas
                    df = pd.read_excel(file_path, engine='openpyxl')
                    df.columns = [str(c).strip() for c in df.columns]
                    
                    data_to_insert = []
                    for _, row in df.iterrows():
                        def get_col_val(col_names, default=''):
                            for name in col_names:
                                if name in df.columns:
                                    val = row[name]
                                    if pd.notna(val):
                                        return str(val).strip()
                            return default

                        p_id = get_col_val(['Pole_ID', 'pole_id', 'id', 'العمود', 'رقم'])
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            continue
                            
                        lat = get_col_val(['Latitude', 'lat', 'خط_العرض', 'عرض'])
                        lng = get_col_val(['Longitude', 'lng', 'طول', 'خط_الطول'])
                        p_name = get_col_val(['Pole_Name', 'name', 'اسم'])
                        qr_img = get_col_val(['QR_image', 'qr', 'صورة_الكيو_ار'])
                        h = get_col_val(['Pole_Height', 'height', 'ارتفاع'])
                        lamp_type = get_col_val(['Lamp_Type', 'lamp', 'قدرة'])
                        p_status = get_col_val(['Pole_Status', 'status', 'حالة العمود'], 'سليم')
                        l_status = get_col_val(['Lamp_Status', 'حالة المصباح'], 'يعمل')
                        door_status = get_col_val(['Door_Status', 'door', 'الباب'], 'مغلق')
                        feeder = get_col_val(['Feeder', 'مغذى'])
                        panel_no = get_col_val(['Panel_No', 'panel', 'قاعدة'])
                        base_depth = get_col_val(['Base_Depth', 'depth', 'عمق'])
                        flange_size = get_col_val(['Flange_Size', 'flange', 'فلانشة'])
                        
                        data_to_insert.append((p_id, lat, lng, p_name, qr_img, h, lamp_type, p_status, l_status, door_status, feeder, panel_no, base_depth, flange_size))

                    if len(data_to_insert) > 0:
                        cursor.execute('DELETE FROM poles')
                        conn.commit()

                        cursor.executemany('''
                            INSERT OR REPLACE INTO poles (pole_ID, Latitude, Longitude, Pole_Name, QR_image, Pole_Height, Lamp_Type, Pole_Status, Lamp_Status, Door_Status, Feeder, Panel_No, Base_Depth, Flange_Size)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', data_to_insert)
                        conn.commit()

                        flash(f'تم استبدال البيانات بنجاح ورفع {len(data_to_insert)} عمود!', 'success')
                    else:
                        flash('الملف لا يحتوي على صفوف صالحة أو مطابقة لأسماء الأعمدة!', 'danger')

                except Exception as e:
                    import traceback
                    conn.rollback()
                    return f"<h3 dir='ltr'>EXCEL UPLOAD ERROR:</h3><pre>{traceback.format_exc()}</pre>", 500

        # 2. خيار إضافة وتحديث البيانات (Append / Merge) بسرعة عالية
        elif action == 'append_excel':
            file = request.files.get('excel_file')
            if file and file.filename.endswith(('.xlsx', '.xls')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                try:
                    df = pd.read_excel(file_path, engine='openpyxl')
                    df.columns = [str(c).strip() for c in df.columns]
                    
                    data_to_insert = []
                    for _, row in df.iterrows():
                        def get_col_val(col_names, default=''):
                            for name in col_names:
                                if name in df.columns:
                                    val = row[name]
                                    if pd.notna(val):
                                        return str(val).strip()
                            return default

                        p_id = get_col_val(['Pole_ID', 'pole_id', 'id', 'العمود', 'رقم'])
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            continue
                            
                        lat = get_col_val(['Latitude', 'lat', 'خط_العرض', 'عرض'])
                        lng = get_col_val(['Longitude', 'lng', 'طول', 'خط_الطول'])
                        p_name = get_col_val(['Pole_Name', 'name', 'اسم'])
                        qr_img = get_col_val(['QR_image', 'qr', 'صورة_الكيو_ار'])
                        h = get_col_val(['Pole_Height', 'height', 'ارتفاع'])
                        lamp_type = get_col_val(['Lamp_Type', 'lamp', 'قدرة'])
                        p_status = get_col_val(['Pole_Status', 'status', 'حالة العمود'], 'سليم')
                        l_status = get_col_val(['Lamp_Status', 'حالة المصباح'], 'يعمل')
                        door_status = get_col_val(['Door_Status', 'door', 'الباب'], 'مغلق')
                        feeder = get_col_val(['Feeder', 'مغذى'])
                        panel_no = get_col_val(['Panel_No', 'panel', 'قاعدة'])
                        base_depth = get_col_val(['Base_Depth', 'depth', 'عمق'])
                        flange_size = get_col_val(['Flange_Size', 'flange', 'فلانشة'])
                        
                        data_to_insert.append((p_id, lat, lng, p_name, qr_img, h, lamp_type, p_status, l_status, door_status, feeder, panel_no, base_depth, flange_size))

                    if len(data_to_insert) > 0:
                        cursor.executemany('''
                            INSERT INTO poles (pole_ID, Latitude, Longitude, Pole_Name, QR_image, Pole_Height, Lamp_Type, Pole_Status, Lamp_Status, Door_Status, Feeder, Panel_No, Base_Depth, Flange_Size)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(pole_ID) DO UPDATE SET
                            Latitude=excluded.Latitude,
                            Longitude=excluded.Longitude,
                            Pole_Name=excluded.Pole_Name,
                            QR_image=excluded.QR_image,
                            Pole_Height=excluded.Pole_Height,
                            Lamp_Type=excluded.Lamp_Type,
                            Pole_Status=excluded.Pole_Status,
                            Lamp_Status=excluded.Lamp_Status,
                            Door_Status=excluded.Door_Status,
                            Feeder=excluded.Feeder,
                            Panel_No=excluded.Panel_No,
                            Base_Depth=excluded.Base_Depth,
                            Flange_Size=excluded.Flange_Size
                        ''', data_to_insert)
                        conn.commit()

                        flash(f'تمت إضافة وتحديث {len(data_to_insert)} عمود بنجاح!', 'success')
                    else:
                        flash('الملف لا يحتوي على صفوف صالحة للإضافة!', 'danger')

                except Exception as e:
                    import traceback
                    conn.rollback()
                    return f"<h3 dir='ltr'>EXCEL APPEND ERROR:</h3><pre>{traceback.format_exc()}</pre>", 500

        elif action == 'delete_pole':
            p_id = request.form.get('pole_ID')
            cursor.execute('DELETE FROM poles WHERE pole_ID = ?', (p_id,))
            conn.commit()
            flash('تم حذف العمود بنجاح', 'info')

    cursor.execute('SELECT * FROM admin_config WHERE id = 1')
    admin_info = cursor.fetchone()
    cursor.execute('SELECT * FROM technicians')
    technicians = cursor.fetchall()

    search = request.args.get('search', '')
    if search:
        cursor.execute("SELECT * FROM poles WHERE pole_ID LIKE ? OR Pole_Name LIKE ? OR Lamp_Type LIKE ?", ('%' + search + '%', '%' + search + '%', '%' + search + '%'))
    else:
        cursor.execute('SELECT * FROM poles')
    
    poles = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard.html', poles=poles, search=search, admin_info=admin_info, technicians=technicians)

@app.route('/pole/<pole_id>')
def pole_detail(pole_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM poles WHERE pole_ID = ?', (pole_id,))
    pole = cursor.fetchone()
    conn.close()
    
    if not pole:
        return "العمود غير موجود", 404
    return render_template('pole_detail.html', pole=pole)

@app.route('/technician/login', methods=['GET', 'POST'])
def technician_login():
    pole_id = request.args.get('pole_id', '')
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        target_pole = request.form.get('pole_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM technicians WHERE username = ? AND password = ?', (u, p))
        tech = cursor.fetchone()
        conn.close()
        
        if tech:
            session['tech_logged'] = True
            session['tech_id'] = tech['id']
            session['tech_username'] = tech['username']
            return redirect(url_for('technician_edit', pole_id=target_pole))
        flash('بيانات دخول الفني خاطئة', 'danger')
    return render_template('technician_login.html', pole_id=pole_id)

@app.route('/technician/edit/<pole_id>', methods=['GET', 'POST'])
def technician_edit(pole_id):
    if 'tech_logged' not in session:
        return redirect(url_for('technician_login', pole_id=pole_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_pole_data':
            status = request.form.get('Pole_Status')
            height = request.form.get('Pole_Height')
            l_type = request.form.get('Lamp_Type')
            ls = request.form.get('Lamp_Status')
            door_status = request.form.get('Door_Status')
            feeder = request.form.get('Feeder')
            panel_no = request.form.get('Panel_No')
            base_depth = request.form.get('Base_Depth')
            flange_size = request.form.get('Flange_Size')
            notes = request.form.get('technician_notes')
            
            cursor.execute('''
                UPDATE poles SET Pole_Height = ?, Lamp_Type = ?, Pole_Status = ?, Lamp_Status = ?, Door_Status = ?, Feeder = ?, Panel_No = ?, Base_Depth = ?, Flange_Size = ?, technician_notes = ?, last_updated = CURRENT_TIMESTAMP
                WHERE pole_ID = ?
            ''', (height, l_type, status, ls, door_status, feeder, panel_no, base_depth, flange_size, notes, pole_id))
            conn.commit()
            flash('تم حفظ تحديثات بيانات العمود بنجاح', 'success')

    cursor.execute('SELECT * FROM poles WHERE pole_ID = ?', (pole_id,))
    pole = cursor.fetchone()
    
    cursor.execute('SELECT * FROM technicians WHERE id = ?', (session.get('tech_id'),))
    my_account = cursor.fetchone()
    
    conn.close()
    
    if not pole:
        return "العمود غير موجود", 404
        
    return render_template('technician_edit.html', pole=pole, my_account=my_account)

@app.route('/technician/logout')
def technician_logout():
    pole_id = request.args.get('pole_id', '')
    session.pop('tech_logged', None)
    session.pop('tech_id', None)
    session.pop('tech_username', None)
    return redirect(url_for('technician_login', pole_id=pole_id))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
