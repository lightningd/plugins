from setuptools import setup
import io

with io.open('README.md', encoding='utf-8') as f:
    long_description = f.read()

with io.open('requirements.txt', encoding='utf-8') as f:
    requirements = [r for r in f.read().split('\n') if len(r)]

setup(name='lightning-qt',
      version='0.1',
      description='clightning gui',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='http://github.com/darosior/lightning-qt',
      author='darosior',
      license='BSD-3-Clause-Clear',
      packages=['lightning', '.', 'forms'],
      scripts=['lightning-qt.py'],
      zip_safe=True,
      install_requires=requirements)
