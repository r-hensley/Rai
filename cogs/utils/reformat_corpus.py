import csv
import logging
import os

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from langdetect import detect as langdetect_detect

from lingua import Language, LanguageDetectorBuilder

from typing import Optional

from sklearn.utils import shuffle


def get_csv(csv_path) -> list[list[str]]:
    # each "line" is like ['4', '0', 'que pasa todos']
    lines = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=' ', quotechar='|')
        for line in reader:
            lines.append(line)
    return lines

def write_csv(csv_path, lines):
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=' ', quotechar='|')
        for line in lines:
            writer.writerow(line)

# english = []
# spanish = []
# if not os.path.exists(f'cogs/utils/principiante.csv'):
#     logging.error("Language detection model not loaded, missing csv files")
#     raise ValueError
# for csv_name in ['principiante.csv', 'avanzado.csv', 'beginner.csv', 'advanced.csv']:
#     rows = get_csv(f"cogs/utils/{csv_name}")
#     newcsv = []
#     # "row" is list like ['4', '0', 'que pasa todos']
#     for row in rows:
#         if len(row[2]) < 10:
#             continue
#         if csv_name in ['principiante.csv', 'avanzado.csv']:
#             spanish.append(row[2])
#         else:
#             english.append(row[2])
#         if len(row[2]) >= 10:
#             newcsv.append(row)
#     # write_csv(f"cogs/utils/corpus/tenchar_{csv_name}", newcsv)

english_train = shuffle([line[2] for line in get_csv("corpus/tenchar_english_train.txt")], random_state=42)
english_test = shuffle([line[2] for line in get_csv("corpus/tenchar_english_test.txt")], random_state=42)
spanish_train = shuffle([line[2] for line in get_csv("corpus/tenchar_spanish_train.txt")], random_state=42)
spanish_test = shuffle([line[2] for line in get_csv("corpus/tenchar_spanish_test.txt")], random_state=42)


def make_set(_english, _spanish, pipeline=None):
    if pipeline:
        eng_pred = pipeline.predict(_english)
        sp_pred = pipeline.predict(_spanish)
        new_english = []
        new_spanish = []
        for i, line in enumerate(_english):
            if eng_pred[i] == 'en':
                new_english.append(line)
            else:
                pass
        for i, line in enumerate(_spanish):
            if sp_pred[i] == 'sp':
                new_spanish.append(line)
        _spanish = new_spanish
        _english = new_english
    
    x = np.array(_english + _spanish)
    y = np.array(['en'] * len(_english) + ['sp'] * len(_spanish))
    
    # x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.05, random_state=42)
    cnt = CountVectorizer(analyzer='char', ngram_range=(2, 2))
    
    pipeline = Pipeline([
        ('vectorizer', cnt),
        ('model', MultinomialNB())
    ])
    
    pipeline.fit(x, y)
    # y_pred = pipeline.predict(x_test)
    # confusion matrix
    # print(confusion_matrix(y_test, y_pred))
    
    return pipeline, _english, _spanish

# my_langdetect_iteration1, english, spanish = make_set(english_train, spanish_train)
# my_langdetect_iteration2, english, spanish = make_set(english, spanish, my_langdetect_iteration1)
# my_langdetect, english, spanish = make_set(english, spanish, my_langdetect_iteration2)

def analyze_results(_english, _spanish, eng_pred, sp_pred):
    # _english: list of english sentences
    # eng_pred: list of predictions for _english ['en, 'en', 'en', 'sp', 'en', ...]
    print(confusion_matrix(['en'] * len(_english) + ['sp'] * len(_spanish), list(eng_pred) + list(sp_pred)))
    print(confusion_matrix(['sp'] * len(_spanish) + ['en'] * len(_english), list(sp_pred) + list(eng_pred)))
    
    print("Incorrect English:")
    for i, line in enumerate(_english):
        if eng_pred[i] != 'en':
            print(eng_pred[i], line)
            
    print("Incorrect Spanish")
    for i, line in enumerate(_spanish):
        if sp_pred[i] != 'sp':
            print(sp_pred[i], line)

# print("Iteration 1")
# analyze_results(english_test, spanish_test, my_langdetect_iteration1.predict(english_test), my_langdetect_iteration1.predict(spanish_test))
# print("Iteration 2")
# analyze_results(english_test, spanish_test, my_langdetect_iteration2.predict(english_test), my_langdetect_iteration2.predict(spanish_test))
# print("Iteration 3")
# analyze_results(english_test, spanish_test, my_langdetect.predict(english_test), my_langdetect.predict(spanish_test))

# def detect_language(text) -> Optional[str]:
#     probs = my_langdetect.predict_proba([text])[0]
#     if probs[0] > 0.9:
#         return 'en'
#     elif probs[0] < 0.1:
#         return 'es'
#     else:
#         return None


lingua_languages_one = [Language.SPANISH, Language.ENGLISH, Language.FRENCH, Language.ARABIC, Language.PORTUGUESE,
                    Language.JAPANESE, Language.TAGALOG, Language.GERMAN, Language.RUSSIAN, Language.ITALIAN]
# lingua_detector = LanguageDetectorBuilder.from_all_languages_with_latin_script().build()
lingua_detector_simple = LanguageDetectorBuilder.from_languages(*lingua_languages_one).build()  # 125 MB
lingua_detector_medium = LanguageDetectorBuilder.from_languages(*(lingua_languages_one + lingua_languages_two)).build()
lingua_detector_full = LanguageDetectorBuilder.from_all_languages().build()
# lingua_detector.compute_language_confidence_values(str)
# lingua_detector.detect_language_of(str)

# 125 MB with just simple
# 126 MB with simple + medium but simple used
# 203 MB with simple + medium but medium used


lingua_eng_pred = []
lingua_sp_pred = []

lingua_detector = lingua_detector_full

for line in english_test:
    pred_conf = lingua_detector.compute_language_confidence_values(line)[:3]
    pred = pred_conf[0].language
    if pred == Language.ENGLISH:
        print("Eng as Eng", pred_conf[0], line)
        lingua_eng_pred.append('en')
    elif pred == Language.SPANISH:
        print("Eng as Sp", pred_conf, line)
        lingua_eng_pred.append('sp')
    else:
        print("Eng as Other", pred_conf, line)
        lingua_eng_pred.append('other')

for line in spanish_test:
    pred_conf = lingua_detector.compute_language_confidence_values(line)[:3]
    pred = pred_conf[0].language
    if pred == Language.ENGLISH:
        print("Sp as Eng", pred_conf, line)
        lingua_sp_pred.append('en')
    elif pred == Language.SPANISH:
        lingua_sp_pred.append('sp')
    else:
        print("Sp as Other", pred_conf, line)
        lingua_sp_pred.append('other')
    
analyze_results(english_test, spanish_test, lingua_eng_pred, lingua_sp_pred)

import time
time.sleep(15)