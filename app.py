import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=os.path.join(basedir, 'templates'), static_folder=os.path.join(basedir, 'static'))

app.config['SECRET_KEY'] = 'makkah_lighting_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'makkah_lighting.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class LightingPole(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pole_id = db.Column(db.String(50), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    pole_name = db.Column(db.String(100))
    pole_height = db.Column(db.String(50))
    lamp_type = db.Column(db.String(50))
    pole_status = db.Column(db.String(50))
    lamp_status = db.Column(db.String(50))
    door_status = db.Column(db.String(50))
    feeder_panel = db.Column(db.String(50))
    base_depth = db.Column(db.String(50))
    flange_size = db.Column(db.String(50))

with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Database Error: {e}")

@app.route('/', methods=['GET', 'POST'])
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        pagination = LightingPole.query.paginate(page=page, per_page=per_page, error_out=False)
        poles = pagination.items
        return render_template('dashboard.html', poles=poles, pagination=pagination)
    except Exception as e:
        return f"<h3>خطأ في القالب:</h3><pre>{str(e)}</pre>", 500

@app.route('/index', methods=['GET', 'POST'])
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    return render_template('login.html')

@app.route('/admin_logout', methods=['GET', 'POST'])
def admin_logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('dashboard'))

@app.route('/upload_csv', methods=['GET', 'POST'])
def upload_csv():
    if request.method == 'GET':
        return redirect(url_for('dashboard'))
        
    if 'file' not in request.files:
        flash('لم يتم اختيار أي ملف', 'danger')
        return redirect(url_for('dashboard'))
    
    file = request.files['file']
    if file.filename == '':
        flash('اسم الملف فارغ', 'danger')
        return redirect(url_for('dashboard'))
    
    if file and file.filename.endswith('.csv'):
        uploads_dir = os.path.join(basedir, 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, file.filename)
        file.save(file_path)
        
        try:
            total_imported = 0
            chunk_size = 500
            
            for chunk in pd.read_csv(file_path, chunksize=chunk_size, encoding='utf-8-sig', on_bad_lines='skip'):
                chunk = chunk.fillna('')
                
                for _, row in chunk.iterrows():
                    p_id = str(row.get('Pole_ID', row.get('pole_id', row.get('ID', '')))).strip()
                    if not p_id:
                        continue
                    
                    pole = LightingPole.query.filter_by(pole_id=p_id).first()
                    if not pole:
                        pole = LightingPole(pole_id=p_id)
                        db.session.add(pole)
                    
                    try:
                        pole.latitude = float(row.get('Latitude', row.get('latitude', 0.0)) or 0.0)
                        pole.longitude = float(row.get('Longitude', row.get('longitude', 0.0)) or 0.0)
                    except:
                        pole.latitude = 0.0
                        pole.longitude = 0.0
                        
                    pole.pole_name = str(row.get('Pole_Name', row.get('pole_name', '')))
                    pole.pole_height = str(row.get('Pole_Height', ''))
                    pole.lamp_type = str(row.get('Lamp_Type', ''))
                    pole.pole_status = str(row.get('Pole_Status', ''))
                    pole.lamp_status = str(row.get('Lamp_Status', ''))
                    pole.door_status = str.get(row.get('Door_Status', '')) if hasattr(str, 'get') else str(row.get('Door_Status', ''))
                    pole.door_status = str(row.get('Door_Status', ''))
                    pole.feeder_panel = str(row.get('Feeder_Panel', ''))
                    pole.base_depth = str(row.get('Base_Depth', ''))
                    pole.flange_size = str(row.get('Flange_Size', ''))
                    
                    total_imported += 1
                
                db.session.commit()
            
            flash(f'تم استيراد وتحديث {total_imported} عمود إنارة بنجاح تام!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'فشل المعالجة بسبب خطأ في بنية الملف: {str(e)}', 'danger')
        
        return redirect(url_for('dashboard'))
    else:
        flash('يرجى رفع ملف بصيغة CSV مدعوم', 'danger')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
