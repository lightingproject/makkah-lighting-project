import os
import qrcode
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'makkah_lighting_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///makkah_lighting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# مجلد تخزين صور الـ QR Codes
QR_FOLDER = os.path.join('static', 'qrcodes')
os.makedirs(QR_FOLDER, exist_ok=True)

# جدول قاعدة البيانات الخاص بأعمدة الإنارة
class LightingPole(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pole_id = db.Column(db.String(50), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    pole_name = db.Column(db.String(100))
    qr_image = db.Column(db.String(200))
    pole_height = db.Column(db.String(50))
    lamp_type = db.Column(db.String(50))
    pole_status = db.Column(db.String(50))
    lamp_status = db.Column(db.String(50))
    door_status = db.Column(db.String(50))
    feeder_panel = db.Column(db.String(50))
    base_depth = db.Column(db.String(50))
    flange_size = db.Column(db.String(50))

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = LightingPole.query.paginate(page=page, per_page=per_page, error_out=False)
    poles = pagination.items
    return render_template('index.html', poles=poles, pagination=pagination)

# مسار رفع ومعالجة ملف الـ CSV على دفعات (Chunks) لمنع انهيار السيرفر واستنزاف الذاكرة
@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        flash('لم يتم اختيار أي ملف', 'danger')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('اسم الملف فارغ', 'danger')
        return redirect(url_for('index'))
    
    if file and file.filename.endswith('.csv'):
        file_path = os.path.join('uploads', file.filename)
        os.makedirs('uploads', exist_ok=True)
        file.save(file_path)
        
        try:
            total_imported = 0
            # قراءة ملف الـ CSV على دفعات (مثلاً 1000 صف في كل دفعة) بترميز يدعم العربية
            chunk_size = 1000
            for chunk in pd.read_csv(file_path, chunksize=chunk_size, encoding='utf-8-sig'):
                # تنظيف الأسماء أو ملء القيم الفارغة لتجنب أخطاء البيانات
                chunk = chunk.fillna('')
                
                for _, row in chunk.iterrows():
                    p_id = str(row.get('Pole_ID', '')).strip()
                    if not p_id:
                        continue
                    
                    # التحقق إذا كان العمود موجوداً مسبقاً لتحديثه أو إضافته
                    pole = LightingPole.query.filter_by(pole_id=p_id).first()
                    
                    # توليد QR Code لكل عمود إنارة
                    qr_filename = f"{p_id}.png"
                    qr_path = os.path.join(QR_FOLDER, qr_filename)
                    if not os.path.exists(qr_path):
                        img = qrcode.make(f"Pole ID: {p_id}")
                        img.save(qr_path)
                    
                    if not pole:
                        pole = LightingPole(pole_id=p_id)
                        db.session.add(pole)
                    
                    pole.latitude = float(row.get('Latitude', 0.0) or 0.0)
                    pole.longitude = float(row.get('Longitude', 0.0) or 0.0)
                    pole.pole_name = str(row.get('Pole_Name', ''))
                    pole.qr_image = url_for('static', filename=f'qrcodes/{qr_filename}')
                    pole.pole_height = str(row.get('Pole_Height', ''))
                    pole.lamp_type = str(row.get('Lamp_Type', ''))
                    pole.pole_status = str(row.get('Pole_Status', ''))
                    pole.lamp_status = str(row.get('Lamp_Status', ''))
                    pole.door_status = str(row.get('Door_Status', ''))
                    pole.feeder_panel = str(row.get('Feeder_Panel', ''))
                    pole.base_depth = str(row.get('Base_Depth', ''))
                    pole.flange_size = str(row.get('Flange_Size', ''))
                    
                    total_imported += 1
                
                # حفظ الدفعة الحالية في قاعدة البيانات لتقليل استهلاك الذاكرة
                db.session.commit()
            
            flash(f'تم استيراد ومعالجة {total_imported} عمود إنارة بنجاح على دفعات!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ أثناء معالجة الملف: {str(e)}', 'danger')
        
        return redirect(url_for('index'))
    else:
        flash('يرجى رفع ملف بصيغة CSV مدعوم بترميز UTF-8', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
