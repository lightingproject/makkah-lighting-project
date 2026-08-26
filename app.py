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
            chunk_size = 500  # تقسيم الدفعات لضمان عدم تجمد السيرفر
            
            # قراءة الملف مع تخطي الأخطاء في الترميز إن وجدت
            for chunk in pd.read_csv(file_path, chunksize=chunk_size, encoding='utf-8-sig', on_bad_lines='skip'):
                chunk = chunk.fillna('')
                
                for _, row in chunk.iterrows():
                    # محاولة جلب معرف العمود بأكثر من احتمال لتجنب اختلاف تسمية الأعمدة
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
                    pole.door_status = str(row.get('Door_Status', ''))
                    pole.feeder_panel = str(row.get('Feeder_Panel', ''))
                    pole.base_depth = str(row.get('Base_Depth', ''))
                    pole.flange_size = str(row.get('Flange_Size', ''))
                    
                    total_imported += 1
                
                db.session.commit()
            
            flash(f'تم استيراد وتحديث {total_imported} عمود إنارة بنجاح تام!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(فشل المعالجة بسبب خطأ في بنية الملف: {str(e)}, 'danger')
        
        return redirect(url_for('dashboard'))
    else:
        flash('يرجى رفع ملف بصيغة CSV مدعوم', 'danger')
        return redirect(url_for('dashboard'))
