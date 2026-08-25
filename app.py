import os
import re
import qrcode
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import sqlite3

app = Flask(__name__)
app.secret_key = 'makkah_lighting_secret_key_2026'

DB_NAME = 'lighting_database.db'
UPLOAD_FOLDER = 'uploads'
QR_FOLDER = 'static/qrs'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS poles (
            pole_ID TEXT PRIMARY KEY,
            Pole_Name TEXT,
            lat TEXT,
            lng TEXT,
            Pole_Height TEXT,
            Fixture_Type TEXT,
            Lamp_Type TEXT,
            Pole_Status TEXT,
            Lamp_Status TEXT,
            Door TEXT,
            Feeder TEXT,
            Panel_Base TEXT,
            Depth TEXT,
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

def generate_qr_code(pole_id):
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(pole_id))
    if not clean_id:
        clean_id = "pole_default"
        
    url = f"https://makkah-lighting-project.onrender.com/pole/{clean_id}"
    
    if not os.path.exists(QR_FOLDER):
        os.makedirs(QR_FOLDER, exist_ok=True)
        
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    qr_path = os.path.join(QR_FOLDER, f"{clean_id}.png")
    img.save(qr_path)

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

        # استبدال البيانات بالكامل بأمان تام
        elif action == 'upload_excel':
            file = request.files.get('excel_file')
            if file and file.filename.endswith(('.xlsx', '.xls')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                try:
                    df = pd.read_excel(file_path, engine='openpyxl')
                    df.columns = [str(c).strip() for c in df.columns]
                    
                    def get_val(row, keywords, default=''):
                        for col in df.columns:
                            col_lower = col.lower()
                            if any(k in col_lower for k in keywords):
                                try:
                                    val = row[col]
                                    return str(val).strip() if pd.notna(val) else default
                                except:
                                    pass
                        return default

                    cursor.execute('DELETE FROM poles')
                    conn.commit()

                    data_to_insert = []
                    for _, row in df.iterrows():
                        p_id = get_val(row, ['pole_id', 'id', 'pole', 'العمود', 'رقم'])
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            try:
                                first_col_val = row[df.columns[0]]
                                p_id = str(first_col_val).strip() if pd.notna(first_col_val) else ''
                            except:
                                p_id = ''
                                
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            continue
                            
                        p_name = get_val(row, ['pole_name', 'name', 'اسم'])
                        lat = get_val(row, ['lat', 'latitude', 'عرض'])
                        lng = get_val(row, ['lng', 'long', 'longitude', 'طول'])
                        h = get_val(row, ['height', 'pole_height', 'ارتفاع'])
                        f = get_val(row, ['fixture', 'fixture_type', 'فانوس', 'كشاف'])
                        l = get_val(row, ['lamp_type', 'lamp', 'لمبة', 'قدرة'])
                        s = get_val(row, ['pole_status', 'status', 'حالة العمود'], 'سليم')
                        ls = get_val(row, ['lamp_status', 'حالة المصباح'], 'يعمل')
                        door = get_val(row, ['door', 'الباب'], 'موجود')
                        feeder = get_val(row, ['feeder', 'مغذى'])
                        panel_base = get_val(row, ['panel_base', 'panel', 'قاعدة'])
                        depth = get_val(row, ['depth', 'عمق'])
                        flange_size = get_val(row, ['flange', 'flange_size', 'فلانشة'])
                        
                        data_to_insert.append((p_id, p_name, lat, lng, h, f, l, s, ls, door, feeder, panel_base, depth, flange_size))
                        generate_qr_code(p_id)

                    cursor.executemany('''
                        INSERT OR REPLACE INTO poles (pole_ID, Pole_Name, lat, lng, Pole_Height, Fixture_Type, Lamp_Type, Pole_Status, Lamp_Status, Door, Feeder, Panel_Base, Depth, Flange_Size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', data_to_insert)
                    conn.commit()

                    flash(f'تم استبدال البيانات ورفع {len(data_to_insert)} عمود بنجاح!', 'success')
                except Exception as e:
                    import traceback
                    conn.rollback()
                    conn.close()
                    return f"<h3 dir='ltr'>EXCEL READ ERROR:</h3><pre>{traceback.format_exc()}</pre>", 500

        # إضافة وتحديث البيانات (دمج) بأمان تام
        elif action == 'append_excel':
            file = request.files.get('excel_file')
            if file and file.filename.endswith(('.xlsx', '.xls')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                try:
                    df = pd.read_excel(file_path, engine='openpyxl')
                    df.columns = [str(c).strip() for c in df.columns]
                    
                    def get_val(row, keywords, default=''):
                        for col in df.columns:
                            col_lower = col.lower()
                            if any(k in col_lower for k in keywords):
                                try:
                                    val = row[col]
                                    return str(val).strip() if pd.notna(val) else default
                                except:
                                    pass
                        return default

                    added_count = 0
                    for _, row in df.iterrows():
                        p_id = get_val(row, ['pole_id', 'id', 'pole', 'العمود', 'رقم'])
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            try:
                                first_col_val = row[df.columns[0]]
                                p_id = str(first_col_val).strip() if pd.notna(first_col_val) else ''
                            except:
                                p_id = ''
                                
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            continue
                            
                        p_name = get_val(row, ['pole_name', 'name', 'اسم'])
                        lat = get_val(row, ['lat', 'latitude', 'عرض'])
                        lng = get_val(row, ['lng', 'long', 'longitude', 'طول'])
                        h = get_val(row, ['height', 'pole_height', 'ارتفاع'])
                        f = get_val(row, ['fixture', 'fixture_type', 'فانوس', 'كشاف'])
                        l = get_val(row, ['lamp_type', 'lamp', 'لمبة', 'قدرة'])
                        s = get_val(row, ['pole_status', 'status', 'حالة العمود'], 'سليم')
                        ls = get_val(row, ['lamp_status', 'حالة المصباح'], 'يعمل')
                        door = get_val(row, ['door', 'الباب'], 'موجود')
                        feeder = get_val(row, ['feeder', 'مغذى'])
                        panel_base = get_val(row, ['panel_base', 'panel', 'قاعدة'])
                        depth = get_val(row, ['depth', 'عمق'])
                        flange_size = get_val(row, ['flange', 'flange_size', 'فلانشة'])
                        
                        cursor.execute('''
                            INSERT INTO poles (pole_ID, Pole_Name, lat, lng, Pole_Height, Fixture_Type, Lamp_Type, Pole_Status, Lamp_Status, Door, Feeder, Panel_Base, Depth, Flange_Size)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(pole_ID) DO UPDATE SET
                            Pole_Name=excluded.Pole_Name,
                            lat=excluded.lat,
                            lng=excluded.lng,
                            Pole_Height=excluded.Pole_Height,
                            Fixture_Type=excluded.Fixture_Type,
                            Lamp_Type=excluded.Lamp_Type,
                            Pole_Status=excluded.Pole_Status,
                            Lamp_Status=excluded.Lamp_Status,
                            Door=excluded.Door,
                            Feeder=excluded.Feeder,
                            Panel_Base=excluded.Panel_Base,
                            Depth=excluded.Depth,
                            Flange_Size=excluded.Flange_Size
                        ''', (p_id, p_name, lat, lng, h, f, l, s, ls, door, feeder, panel_base, depth, flange_size))
                        generate_qr_code(p_id)
                        added_count += 1

                    conn.commit()
                    flash(f'تمت إضافة وتحديث {added_count} عمود بنجاح!', 'success')
                except Exception as e:
                    import traceback
                    conn.rollback()
                    conn.close()
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
            f_type = request.form.get('Fixture_Type')
            l_type = request.form.get('Lamp_Type')
            ls = request.form.get('Lamp_Status')
            door = request.form.get('Door')
            feeder = request.form.get('Feeder')
            panel_base = request.form.get('Panel_Base')
            depth = request.form.get('Depth')
            flange_size = request.form.get('Flange_Size')
            notes = request.form.get('technician_notes')
            
            cursor.execute('''
                UPDATE poles SET Pole_Height = ?, Fixture_Type = ?, Lamp_Type = ?, Pole_Status = ?, Lamp_Status = ?, Door = ?, Feeder = ?, Panel_Base = ?, Depth = ?, Flange_Size = ?, technician_notes = ?, last_updated = CURRENT_TIMESTAMP
                WHERE pole_ID = ?
            ''', (height, f_type, l_type, status, ls, door, feeder, panel_base, depth, flange_size, notes, pole_id))
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
