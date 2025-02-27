# -*- coding: utf-8 -*-

import os
import glob
import json
import logging
import subprocess
import datetime as dt

import camelot
from camelot.core import TableList
from camelot.parsers import Lattice, Stream
from camelot.ext.ghostscript import Ghostscript

from . import configuration as conf
from .models import File, Rule, Job
from .settings import Session
from .utils.file import mkdirs
from .utils.task import (get_pages, save_page, get_page_layout, get_file_dim,
                         get_image_dim)


def split(file_id):
    try:
        session = Session()
        file = session.query(File).filter(File.file_id == file_id).first()
        
        extract_pages, total_pages = get_pages(file.filepath, file.pages)
        parent_folder=os.path.join(conf.PDFS_FOLDER, file_id,'')
        # extract into single-page PDFs
        gs_call = 'gs -q -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -o {}page-%d.pdf {}'.format(parent_folder,file.filepath)
        gs_call = gs_call.encode().split()
        null = open(os.devnull, 'wb')
        with Ghostscript(*gs_call, stdout=null) as gs:
            pass
        # PDF to PNG files for each page
        gs_call = 'gs -q -sDEVICE=png16m -o {}page-%d.png -r300 {}'.format(parent_folder,file.filepath)
        gs_call = gs_call.encode().split()
        with Ghostscript(*gs_call, stdout=null) as gs:
            pass
        null.close()

        filenames, filepaths, imagenames, imagepaths, filedims, imagedims, detected_areas = ({} for i in range(7))
        for page in extract_pages:
            filename = 'page-{}.pdf'.format(page)
            filepath = os.path.join(conf.PDFS_FOLDER, file_id, filename)
            imagename = ''.join([filename.replace('.pdf', ''), '.png'])
            imagepath = os.path.join(conf.PDFS_FOLDER, file_id, imagename)

            filenames[page] = filename
            filepaths[page] = filepath
            imagenames[page] = imagename
            imagepaths[page] = imagepath
            filedims[page] = get_file_dim(filepath)
            imagedims[page] = get_image_dim(imagepath)

            lattice_areas, stream_areas = (None for i in range(2))
            # lattice
            parser = Lattice()
            tables = parser.extract_tables(filepath)
            if len(tables):
                lattice_areas = []
                for table in tables:
                    x1, y1, x2, y2 = table._bbox
                    lattice_areas.append((x1, y2, x2, y1))
            # stream
            parser = Stream()
            tables = parser.extract_tables(filepath)
            if len(tables):
                stream_areas = []
                for table in tables:
                    x1, y1, x2, y2 = table._bbox
                    stream_areas.append((x1, y2, x2, y1))

            detected_areas[page] = {
                'lattice': lattice_areas, 'stream': stream_areas}

        file.extract_pages = json.dumps(extract_pages)
        file.total_pages = total_pages
        file.has_image = True
        file.filenames = json.dumps(filenames)
        file.filepaths = json.dumps(filepaths)
        file.imagenames = json.dumps(imagenames)
        file.imagepaths = json.dumps(imagepaths)
        file.filedims = json.dumps(filedims)
        file.imagedims = json.dumps(imagedims)
        file.detected_areas = json.dumps(detected_areas)

        session.commit()
        session.close()
    except Exception as e:
        logging.exception(e)


def extract(job_id):
    try:
        session = Session()
        job = session.query(Job).filter(Job.job_id == job_id).first()
        rule = session.query(Rule).filter(Rule.rule_id == job.rule_id).first()
        file = session.query(File).filter(File.file_id == job.file_id).first()

        parent_folder = os.path.join(conf.PDFS_FOLDER, file.file_id, '')
        docs = os.listdir(parent_folder)
        docs = sorted(list(map(lambda x: os.path.join(parent_folder, x),
                               filter(lambda x: x[0:4] == "file", docs))))

        rule_options = json.loads(rule.rule_options)
        flavor = rule_options.pop('flavor')
        pages = rule_options.pop('pages')

        filepaths = json.loads(file.filepaths)
        filepaths_as_list=list(filepaths.values())
       
        tables = []
        i = 0
        for doc in docs:
            for f in filepaths_as_list:
                os.remove(f)
            gs_call = 'gs -q -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -o {}page-%d.pdf {}'.format(
                parent_folder, doc)
            gs_call = gs_call.encode().split()
            null = open(os.devnull, 'wb')
            with Ghostscript(*gs_call, stdout=null) as gs:
                pass
            null.close()
            for p in pages:
                kwargs = pages[p]
                kwargs.update(rule_options)
                parser = Lattice(
                    **kwargs) if flavor.lower() == 'lattice' else Stream(**kwargs)
                t = parser.extract_tables(filepaths[p])
                for _t in t:
                    _t.page = int(p)+i
                tables.extend(t)
            i += len(pages)

        tables = TableList(tables)

        froot, fext = os.path.splitext(file.filename)
        datapath = os.path.dirname(file.filepath)
        for f in ['csv', 'excel', 'json', 'html']:
            f_datapath = os.path.join(datapath, f)
            mkdirs(f_datapath)
            ext = f if f != 'excel' else 'xlsx'
            f_datapath = os.path.join(f_datapath, '{}.{}'.format(froot, ext))
            tables.export(f_datapath, f=f, compress=True)

        # for render
        jsonpath = os.path.join(datapath, 'json')
        jsonpath = os.path.join(jsonpath, '{}.json'.format(froot))
        tables.export(jsonpath, f='json')
        render_files = {os.path.splitext(os.path.basename(f))[0]: f
            for f in glob.glob(os.path.join(datapath, 'json/*.json'))}

        job.datapath = datapath
        job.render_files = json.dumps(render_files)
        job.is_finished = True
        job.finished_at = dt.datetime.now()

        session.commit()
        session.close()
    except Exception as e:
        logging.exception(e)


def merge(file_id):
    try:
        parent_folder=os.path.join(conf.PDFS_FOLDER, file_id,'')
        docs=os.listdir(parent_folder)
        docs=" ".join(map(lambda x: os.path.join(parent_folder,x), docs))
        gs_call = 'gs -q -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -o {}concat.pdf {}'.format(parent_folder,docs)
        gs_call = gs_call.encode().split()
        null = open(os.devnull, 'wb')
        with Ghostscript(*gs_call, stdout=null) as gs:
            pass
        null.close()
    except Exception as e:
        logging.exception(e)
