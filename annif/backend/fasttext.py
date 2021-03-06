"""Annif backend using the fastText classifier"""

import collections
import os.path
import annif.util
from annif.suggestion import SubjectSuggestion, ListSuggestionResult
from annif.exception import NotInitializedException, NotSupportedException
import fastText
from . import backend
from . import mixins


class FastTextBackend(mixins.ChunkingBackend, backend.AnnifBackend):
    """fastText backend for Annif"""

    name = "fasttext"
    needs_subject_index = True

    FASTTEXT_PARAMS = {
        'lr': float,
        'lrUpdateRate': int,
        'dim': int,
        'ws': int,
        'epoch': int,
        'minCount': int,
        'neg': int,
        'wordNgrams': int,
        'loss': str,
        'bucket': int,
        'minn': int,
        'maxn': int,
        'thread': int,
        't': float
    }

    DEFAULT_PARAMS = {
        'dim': 100,
        'lr': 0.25,
        'epoch': 5,
        'loss': 'hs',
    }

    MODEL_FILE = 'fasttext-model'
    TRAIN_FILE = 'fasttext-train.txt'

    # defaults for uninitialized instances
    _model = None

    def default_params(self):
        params = backend.AnnifBackend.DEFAULT_PARAMS.copy()
        params.update(mixins.ChunkingBackend.DEFAULT_PARAMS)
        params.update(self.DEFAULT_PARAMS)
        return params

    def initialize(self):
        if self._model is None:
            path = os.path.join(self.datadir, self.MODEL_FILE)
            self.debug('loading fastText model from {}'.format(path))
            if os.path.exists(path):
                self._model = fastText.load_model(path)
                self.debug('loaded model {}'.format(str(self._model)))
                self.debug('dim: {}'.format(self._model.get_dimension()))
            else:
                raise NotInitializedException(
                    'model {} not found'.format(path),
                    backend_id=self.backend_id)

    @staticmethod
    def _id_to_label(subject_id):
        return "__label__{:d}".format(subject_id)

    def _label_to_subject(self, label):
        labelnum = label.replace('__label__', '')
        subject_id = int(labelnum)
        return self.project.subjects[subject_id]

    def _write_train_file(self, doc_subjects, filename):
        with open(filename, 'w', encoding='utf-8') as trainfile:
            for doc, subject_ids in doc_subjects.items():
                labels = [self._id_to_label(sid) for sid in subject_ids
                          if sid is not None]
                if labels:
                    print(' '.join(labels), doc, file=trainfile)
                else:
                    self.warning('no labels for document "{}"'.format(doc))

    def _normalize_text(self, text):
        return ' '.join(self.project.analyzer.tokenize_words(text))

    def _create_train_file(self, corpus):
        self.info('creating fastText training file')

        doc_subjects = collections.defaultdict(set)

        for doc in corpus.documents:
            text = self._normalize_text(doc.text)
            if text == '':
                continue
            doc_subjects[text] = [self.project.subjects.by_uri(uri)
                                  for uri in doc.uris]

        annif.util.atomic_save(doc_subjects,
                               self.datadir,
                               self.TRAIN_FILE,
                               method=self._write_train_file)

    def _create_model(self, params):
        self.info('creating fastText model')
        trainpath = os.path.join(self.datadir, self.TRAIN_FILE)
        modelpath = os.path.join(self.datadir, self.MODEL_FILE)
        params = {param: self.FASTTEXT_PARAMS[param](val)
                  for param, val in params.items()
                  if param in self.FASTTEXT_PARAMS}
        self.debug('Model parameters: {}'.format(params))
        self._model = fastText.train_supervised(trainpath, **params)
        self._model.save_model(modelpath)

    def _train(self, corpus, params):
        if corpus.is_empty():
            raise NotSupportedException('training backend {} with no documents'
                                        .format(self.backend_id))
        self._create_train_file(corpus)
        self._create_model(params)

    def _predict_chunks(self, chunktexts, limit):
        return self._model.predict(list(
            filter(None, [self._normalize_text(chunktext)
                          for chunktext in chunktexts])), limit)

    def _suggest_chunks(self, chunktexts, params):
        limit = int(params['limit'])
        chunklabels, chunkscores = self._predict_chunks(
            chunktexts, limit)
        label_scores = collections.defaultdict(float)
        for labels, scores in zip(chunklabels, chunkscores):
            for label, score in zip(labels, scores):
                label_scores[label] += score
        best_labels = sorted([(score, label)
                              for label, score in label_scores.items()],
                             reverse=True)

        results = []
        for score, label in best_labels[:limit]:
            subject = self._label_to_subject(label)
            results.append(SubjectSuggestion(
                uri=subject[0],
                label=subject[1],
                score=score / len(chunktexts)))
        return ListSuggestionResult(results, self.project.subjects)
