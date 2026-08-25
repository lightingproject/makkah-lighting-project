import os
import qrcode
import pandas as pd
import io
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
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
            Pole_Height TEXT,
            Fixture_Type TEXT,
            Lamp_Type TEXT,
            Pole_Status TEXT,
            lat TEXT,
            lng TEXT,
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
    safe_id = str(pole_id).strip().replace('/', '_').replace('\\', '_')
    url = f"https://makkah-lighting-project.onrender.com/pole/{safe_id}"
    img = qrcode.make(url)
    qr_path = os.path.join(QR_FOLDER, f"{safe_id}.png")
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

        elif action == 'upload_excel':
            file = request.files.get('excel_file')
            if file and file.filename.endswith(('.xlsx', '.xls')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                try:
                    df = pd.read_excel(file_path, engine='openpyxl')
                    df.columns = [str(c).strip().lower() for c in df.columns]
                    
                    def find_col(keywords):
                        for col in df.columns:
                            if any(k in col for k in keywords):
                                return col
                        return None

                    id_col = find_col(['pole_id', 'id', 'pole', 'العمود', 'رقم']) or df.columns[0]
                    h_col = find_col(['height', 'pole_height', 'ارتفاع'])
                    f_col = find_col(['fixture', 'fixture_type', 'فانوس', 'كشاف'])
                    l_col = find_col(['lamp', 'lamp_type', 'لمبة', 'قدرة'])
                    s_col = find_col(['status', 'pole_status', 'حالة'])
                    lat_col = find_col(['lat', 'latitude'])
                    lng_col = find_col(['lng', 'long', 'longitude'])

                    data_to_insert = []
                    for _, row in df.iterrows():
                        p_id = str(row[id_col]).strip() if pd.notna(row[id_col]) else ''
                        if not p_id or p_id.lower() == 'nan' or p_id == '':
                            continue
                            
                        h = str(row[h_col]).strip() if h_col and pd.notna(row[h_col]) else ''
                        f = str(row[f_col]).strip() if f_col and pd.notna(row[f_col]) else ''
                        l = str(row[l_col]).strip() if l_col and pd.notna(row[l_col]) else ''
                        s = str(row[s_col]).strip() if s_col and pd.notna(row[s_col]) else 'سليم'
                        lat = str(row[lat_col]).strip() if lat_col and pd.notna(row[lat_col]) else ''
                        lng = str(row[lng_col]).strip() if lng_col and pd.notna(row[lng_col]) else ''
                        
                        data_to_insert.append((p_id, h, f, l, s, lat, lng))

                    batch_size = 500
                    for i in range(0, len(data_to_insert), batch_size):
                        batch = data_to_insert[i:i + batch_size]
                        cursor.executemany('''
                            INSERT INTO poles (pole_ID, Pole_Height, Fixture_Type, Lamp_Type, Pole_Status, lat, lng)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(pole_ID) DO UPDATE SET
                            Pole_Height=excluded.Pole_Height,
                            Fixture_Type=excluded.Fixture_Type,
                            Lamp_Type=excluded.Lamp_Type,
                            Pole_Status=excluded.Pole_Status,
                            lat=excluded.lat,
                            lng=excluded.lng
                        ''', batch)
                        conn.commit()

                    flash(f'تم رفع وتحديث {len(data_to_insert)} عمود بنجاح تام وتحديث الجدول!', 'success')
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    return f"<h3 dir='ltr'>ERROR DETAILS:</h3><pre>{error_details}</pre>", 500

        elif action == 'add_pole':
            p_id = request.form.get('pole_ID')
            height = request.form.get('Pole_Height')
            f_type = request.form.get('Fixture_Type')
            l_type = request.form.get('Lamp_Type')
            status = request.form.get('Pole_Status')
            lat = request.form.get('lat')
            lng = request.form.get('lng')
            try:
                cursor.execute('''
                    INSERT INTO poles (pole_ID, Pole_Height, Fixture_Type, Lamp_Type, Pole_Status, lat, lng)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (p_id, height, f_type, l_type, status, lat, lng))
                conn.commit()
                generate_qr_code(p_id)
                flash('تم إضافة العمود وتوليد الـ QR بنجاح', 'success')
            except:
                flash('معرف العمود موجود مسبقاً', 'danger')

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
        cursor.execute("SELECT * FROM poles WHERE pole_ID LIKE ? OR Lamp_Type LIKE ?", ('%' + search + '%', '%' + search + '%'))
    else:
        cursor.execute('SELECT * FROM poles')
    
    poles = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard.html', poles=poles, search=search, admin_info=admin_info, technicians=technicians)

@app.route('/download_all_qrs')
def download_all_qrs():
    """تنبيه بديل لمنع حدوث خطأ 504 Time-out على السيرفر المجاني"""
    if 'admin_logged' not in session:
        return redirect(url_for('admin_login'))
    flash('خاصية تحميل كافة الأكواد دفعة واحدة تم إيقافها مؤقتاً لتجنب ضغط الخادم. يمكنك طباعة أو حفظ كود أي عمود من صفحة تفاصيل العمود المخصصة له مباشرة.', 'warning')
    return redirect(url_for('dashboard'))

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
        if action == 'update_my_account':
            new_u = request.form.get('new_username')
            new_p = request.form.get('new_password')
            t_id = session.get('tech_id')
            try:
                cursor.execute('UPDATE technicians SET username = ?, password = ? WHERE id = ?', (new_u, new_p, t_id))
                conn.commit()
                session['tech_username'] = new_u
                flash('تم تحديث بيانات حسابك الشخصي بنجاح', 'success')
            except:
                flash('اسم المستخدم الجديد مستخدم مسبقاً', 'danger')
                
        elif action == 'update_pole_data':
            status = request.form.get('Pole_Status')
            height = request.form.get('Pole_Height')
            f_type = request.form.get('Fixture_Type')
            l_type = request.form.get('Lamp_Type')
            notes = request.form.get('technician_notes')
            
            cursor.execute('''
                UPDATE poles SET Pole_Height = ?, Fixture_Type = ?, Lamp_Type = ?, Pole_Status = ?, technician_notes = ?, last_updated = CURRENT_TIMESTAMP
                WHERE pole_ID = ?
            ''', (height, f_type, l_type, status, notes, pole_id))
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
