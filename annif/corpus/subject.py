"""Classes for supporting subject corpora expressed as directories or files"""

import abc
import collections
import glob
import os
import os.path
import shutil
import annif.util
from annif import logger


Subject = collections.namedtuple('Subject', 'uri label text')


class SubjectCorpus(metaclass=abc.ABCMeta):
    """Abstract base class for subject corpora"""

    @property
    @abc.abstractmethod
    def subjects(self):
        """Iterate through the subject corpus, yielding Subject objects."""
        pass


class SubjectDirectory(SubjectCorpus):
    """A subject corpus in the form of a directory with .txt files."""

    def __init__(self, path):
        self.path = path
        self._filenames = sorted(glob.glob(os.path.join(path, '*.txt')))

    @property
    def subjects(self):
        for filename in self._filenames:
            with open(filename) as subjfile:
                uri, label = subjfile.readline().strip().split(' ', 1)
                text = ' '.join(subjfile.readlines())
                yield Subject(uri=uri, label=label, text=text)

    @classmethod
    def _add_subject(cls, uri, text, subjectdir, subject_index):
        filename = '{}.txt'.format(annif.util.localname(uri))
        path = os.path.join(subjectdir, filename)
        if not os.path.exists(path):
            subject_id = subject_index.by_uri(uri)
            label = subject_index[subject_id][1]
            with open(path, 'w') as subjfile:
                print("{} {}".format(uri, label), file=subjfile)
        with open(path, 'a') as subjfile:
            print(text, file=subjfile)

    @classmethod
    def from_documents(cls, subjectdir, docfile, subject_index):
        # clear the subject directory
        shutil.rmtree(subjectdir, ignore_errors=True)
        os.makedirs(subjectdir)

        for text, uris in docfile:
            for uri in uris:
                cls._add_subject(uri, text, subjectdir, subject_index)

        return SubjectDirectory(subjectdir)


class SubjectFileTSV(SubjectCorpus):
    """A subject corpus stored in a TSV file."""

    def __init__(self, path):
        self.path = path

    @property
    def subjects(self):
        with open(self.path) as subjfile:
            for line in subjfile:
                uri, label = line.strip().split(None, 1)
                clean_uri = annif.util.cleanup_uri(uri)
                yield Subject(uri=clean_uri, label=label, text=None)


class SubjectIndex:
    """An index that remembers the associations between integers subject IDs
    and their URIs and labels."""

    def __init__(self, corpus):
        """Initialize the subject index from a subject corpus."""
        self._uris = []
        self._labels = []
        self._uri_idx = {}
        for subject_id, subject in enumerate(corpus.subjects):
            self._uris.append(subject.uri)
            self._labels.append(subject.label)
            self._uri_idx[subject.uri] = subject_id

    def __len__(self):
        return len(self._uris)

    def __getitem__(self, subject_id):
        return (self._uris[subject_id], self._labels[subject_id])

    def by_uri(self, uri):
        """return the subject index of a subject by its URI"""
        try:
            return self._uri_idx[uri]
        except KeyError:
            logger.warning('Unknown subject URI <%s>', uri)
            return None

    def save(self, path):
        """Save this subject index into a file."""

        with open(path, 'w') as subjfile:
            for subject_id in range(len(self)):
                line = "<{}>\t{}".format(
                    self._uris[subject_id], self._labels[subject_id])
                print(line, file=subjfile)

    @classmethod
    def load(cls, path):
        """Load a subject index from a TSV file and return it."""

        corpus = SubjectFileTSV(path)
        return cls(corpus)
