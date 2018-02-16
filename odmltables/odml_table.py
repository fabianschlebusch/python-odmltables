# -*- coding: utf-8 -*-
"""

"""
import os
import re
import copy
import odml
import csv
import datetime
import xlrd

from future.utils import iteritems

# Workaround Python 2 and 3 unicode handling.
try:
    unicode = unicode
except NameError:
    unicode = str


class OdmlTable(object):
    """
    Class to create tables in different formats from odml-files


    :param show_all_sections: if set to False, information about the section
        like the path or name of the section wont be in the table again, if
        they are same as in the line before
    :param show_all_properties: if set to False, information about the property
        like the name or definition of the property wont be in the table again,
        if they are same as in the line before
        tables with an emptycolumn
    :type show_all_sections: bool
    :type show_all_properties: bool

    """

    def __init__(self, load_from=None):

        self._odmldict = None
        self._docdict = None
        self.odtypes = OdmlDtypes()
        self._header = ["Path", "PropertyName", "Value", "odmlDatatype"]
        self._header_titles = {"Path": "Path to Section",
                               "SectionName": "Section Name",
                               "SectionType": "Section Type",
                               "SectionDefinition": "Section Definition",
                               "PropertyName": "Property Name",
                               "PropertyDefinition": "Property Definition",
                               "Value": "Value",
                               "DataUnit": "Data Unit",
                               "DataUncertainty": "Data Uncertainty",
                               "odmlDatatype": "odML Data Type"}
        self.show_all_sections = False
        self.show_all_properties = False
        self._SECTION_INF = ["Path", "SectionType", "SectionDefinition"]
        self._PROPERTY_INF = ["PropertyDefinition", "DataUnit", "DataUncertainty", "odmlDatatype"]

        if load_from is not None:
            filename, file_extension = os.path.splitext(load_from)
            if file_extension=='.odml':
                self.load_from_file(load_from)
            elif file_extension=='.xls':
                self.load_from_xls_table(load_from)
            elif file_extension=='.csv':
                self.load_from_csv_table(load_from)
            else:
                raise IOError('Can not read file format "%s". odMLtables '
                              'supports only .odml, .xls and .csv files.')

    def __create_odmldict(self, doc):
        """
        function to create the odml-dict
        """
        # In odml 1.4 properties are the leaves of the odml tree; unwrap from there.
        props = list(doc.iterproperties())

        odmldict = [{'Path': p.get_path(),
                     'SectionType': p.parent.type,
                     'SectionDefinition': p.parent.definition,
                     'PropertyDefinition': p.definition,
                     # Since value now returns a list the check for bool might be useless.
                     'Value': p.value if type(p.value) is not bool else str(p.value),
                     'DataUnit': p.unit,
                     'DataUncertainty': p.uncertainty,
                     'odmlDatatype': p.dtype}
                    for p in props]

        odmldict = self._sort_odmldict(odmldict)
        return odmldict

    def _sort_odmldict(self, odmldict):
        return sorted(odmldict, key=lambda x: x['Path'])

    def _split_path(self, dic):
        path, property_name = dic['Path'].split(':')
        section_name = path.split('/')[-1]
        return path, section_name, property_name

    def _create_documentdict(self, doc):
        attributes = ['author', 'date', 'repository', 'version']
        docdict = {att: getattr(doc, att) for att in attributes}
        return docdict


        # TODO: better exception

    def load_from_file(self, load_from):
        """
        loads the odml-data from an odml-file

        :param load_from: the path to the odml-file
        :type load_from: string

        """
        doc = odml.load(load_from)
        self._odmldict = self.__create_odmldict(doc)
        self._docdict = self._create_documentdict(doc)

    def load_from_odmldoc(self, doc):
        """
        loads the odml-data from an odml-document

        :param load_from: the odml-document
        :type load_from: odml-document
        """
        self._odmldict = self.__create_odmldict(doc)
        self._docdict = self._create_documentdict(doc)

    def load_from_function(self, odmlfct):
        """
        loads the odml-data by using a function that creates an odml-document

        :param load_from: function that returns an odml-document
        :type load_from: function
        """
        doc = odmlfct()
        self._odmldict = self.__create_odmldict(doc)
        self._docdict = self._create_documentdict(doc)

    def _get_docdict(self, row):
        '''
        supplementory function to reconstruct self._docdict from first row in
        table

        :param row: list of values in first row of table
        :return: None
        '''
        if self._docdict == None:
            self._docdict = {}
        for col_id in list(range(int(len(row) / 2))):
            if row[2 * col_id + 1] != '':
                key = row[2 * col_id + 1]
                # in case last entry was empty and document
                # info is longer than header, this cell will
                # not be present
                if 2 * col_id + 2 == len(row):
                    value = ''
                else:
                    value = row[2 * col_id + 2]
                self._docdict[key] = value

    @staticmethod
    def get_xls_header(load_from):
        '''
        Providing non-empty xls header entries of first sheet for odml tables
        gui only
        :return:
        '''
        workbook = xlrd.open_workbook(load_from)

        for sheet_name in workbook.sheet_names():
            worksheet = workbook.sheet_by_name(sheet_name)

            row = 0
            # read document information if present
            if worksheet.cell(0, 0).value == 'Document Information':
                # doc_row = [r.value for r in worksheet.row(row)]
                # self._get_docdict(doc_row)
                row += 1

            # get number of non-empty odml colums
            header_row = worksheet.row(row)

            # read the header
            header = [h.value for h in header_row if h.ctype != 0]

            return header

    def load_from_xls_table(self, load_from):
        """
        loads the odml-data from a xls-file. To load the odml, at least Value,
        Path, PropertyName and odmlDatatype must be given in the table. Also,
        the header_titles must be correct

        :param load_from: name(path) of the xls-file
        :type load_from: string
        """

        self._odmldict = []
        # create a inverted header_titles dictionary for an inverted lookup
        inv_header_titles = {v: k for (k, v) in list(self._header_titles.items())}

        workbook = xlrd.open_workbook(load_from)
        for sheet_name in workbook.sheet_names():
            worksheet = workbook.sheet_by_name(sheet_name)
            row_id = 0

            # read document information if present
            if worksheet.cell(0, 0).value == 'Document Information':
                doc_row = [r.value for r in worksheet.row(row_id)]
                self._get_docdict(doc_row)
                row_id += 1

            # get number of non-empty odml colums
            header_row = worksheet.row(row_id)

            # read the header
            header = [h.value for h in header_row]
            # strip trailing empty cells from header
            for i in list(range(len(header_row) - 1, -1, -1)):
                if header_row[i].ctype == 0:
                    header.pop(i)
                else:
                    break

            n_cols = len(header)
            try:
                self._header = [inv_header_titles[h] if h != '' else None for h in header]
            except KeyError as e:
                if hasattr(e, 'message'):
                    m = e.message
                else:
                    m = str(e)
                raise ValueError('%s is not a valid header title.'%m)
            row_id += 1

            # get column ids of non-empty header cells
            header_title_ids = {h: id for id, h in
                                enumerate(self._header) if h != ''}
            header_title_order = {id: h for id, h in
                                  enumerate(self._header) if h != ''}

            must_haves = ["Path", "PropertyName", "Value", "odmlDatatype"]

            # check, if all of the needed information are in the table
            if any([(m not in self._header) for m in must_haves]):
                err_msg = ("your table has to contain all of the following " +
                           " attributes: {0}").format(must_haves)
                raise ValueError(err_msg)

            current_dic = {"Path": "",
                           "SectionType": "",
                           "SectionDefinition": "",
                           "PropertyDefinition": "",
                           "Value": "",
                           "DataUnit": "",
                           "DataUncertainty": "",
                           "odmlDatatype": ""}

            header_end_row_id = row_id
            for row_id in range(header_end_row_id, worksheet.nrows):
                row = worksheet.row_values(row_id)
                is_new_property = False
                new_dic = {}

                for col_n in list(range(len(row))):
                    # using only columns with header
                    if col_n in header_title_order and header_title_order[col_n] is not None:
                        new_dic[header_title_order[col_n]] = row[col_n]

                # update path and remove section and property names
                new_dic['Path'] = new_dic['Path'] + ':' + new_dic['PropertyName']
                new_dic.pop('PropertyName')
                new_dic.pop('SectionName')

                # convert to python datatypes
                dtype = new_dic['odmlDatatype']
                value = new_dic['Value']
                if ('date' in dtype or 'time' in dtype) and (value != ''):
                    if isinstance(value,float):
                                    value = xlrd.xldate_as_tuple(value, workbook.datemode)
                    elif isinstance(value, unicode):
                        # try explicit conversion of unicode like '2000-03-23'
                        m = re.match('(?P<year>[0-9]{4})-(?P<month>[0-1][0-9])-'
                                     '(?P<day>[0-3][0-9])',
                                     value)
                        if m:
                            date_dict = m.groupdict()
                            value = (int(date_dict['year']),
                                     int(date_dict['month']),
                                     int(date_dict['day']),
                                     0,0,0)
                    else:
                        raise TypeError('Expected xls date or time object, '
                                        'but got instead %s of %s'
                                        ''%(value,type(value)))
                new_dic['Value'] = [self.odtypes.to_odml_value(value, dtype)]

                if (new_dic['Path'].split(':')[0] == ''
                    or current_dic['Path'].split(':')[0] == new_dic['Path'].split(':')[0]):
                    # it is not the start of a new section

                    if new_dic['Path'] == '' or (current_dic['Path'] == new_dic['Path']):
                        # old section, old property
                        current_dic['Value'].extend(new_dic['Value'])
                    else:
                        # old section, new property
                        for key in self._PROPERTY_INF:
                            current_dic[key] = new_dic[key]
                        is_new_property = True
                else:
                    is_new_property = True

                if is_new_property and row_id > header_end_row_id:
                    self._odmldict.append(copy.deepcopy(current_dic))
                    current_dic = new_dic

            # copy final property
            if row_id <= header_end_row_id:
                self._odmldict.append(copy.deepcopy(new_dic))
            else:
                self._odmldict.append(copy.deepcopy(current_dic))
        self._odmldict = self._sort_odmldict(self._odmldict)

    @staticmethod
    def get_csv_header(load_from):
        '''
        Providing non-empty csv header entries of first sheet for odml tables
        gui only
        :return:
        '''
        with open(load_from, 'r') as csvfile:
            csvreader = csv.reader(csvfile)

            row = next(csvreader)

            # check if first line contains document information
            if row[0] == 'Document Information':
                try:
                    row = next(csvreader)
                except StopIteration():
                    raise IOError('Csv file does not contain header row.'
                                  ' Filename "%s"' % load_from)

            # get column ids of non-empty header cells
            header = [h for h in row if h != '']

            return header

    # TODO: use normal reader instead of dictreader => much easier!!
    def load_from_csv_table(self, load_from):
        """
        loads the odmldict from a csv-file containing an odml-table. To load
        the odml, at least Value, Path, PropertyName and odmlDatatype must be
        given in the table. Also, the header_titles must be correct

        :param load_from: name(path) of the csv-file
        :type load_from: string
        """

        self._odmldict = []
        # create a inverted header_titles dictionary for an inverted lookup
        inv_header_titles = {v: k for (k, v) in list(self._header_titles.items())}

        with open(load_from, 'r') as csvfile:
            csvreader = csv.reader(csvfile)

            row = next(csvreader)

            # check if first line contains document information
            if row[0] == 'Document Information':
                self._get_docdict(row)
                try:
                    row = next(csvreader)
                except StopIteration():
                    raise IOError('Csv file does not contain header row.'
                                  ' Filename "%s"' % load_from)

            # get column ids of non-empty header cells
            header_title_ids = {inv_header_titles[h]: id for id, h in
                                enumerate(row) if h != ''}
            header_title_order = {id: inv_header_titles[h] for id, h in
                                  enumerate(row) if h != ''}

            # reconstruct headers
            self._header = [inv_header_titles[h] if h != '' else None for h in row]

            must_haves = ["Path", "PropertyName", "Value", "odmlDatatype"]

            # check, if all of the needed information are in the table
            if any([(m not in self._header) for m in must_haves]):
                err_msg = ("your table has to contain all of the following " +
                           " attributes: {0}").format(must_haves)
                raise ValueError(err_msg)

            current_dic = {"Path": "",
                           "SectionType": "",
                           "SectionDefinition": "",
                           "PropertyDefinition": "",
                           "Value": "",
                           "DataUnit": "",
                           "DataUncertainty": "",
                           "odmlDatatype": ""}

            for row_id, row in enumerate(csvreader):
                is_new_property = False
                new_dic = {}

                # current_dic = {"Path": "",
                #                "SectionType": "",
                #                "SectionDefinition": "",
                #                "PropertyDefinition": "",
                #                "Value": "",
                #                "DataUnit": "",
                #                "DataUncertainty": "",
                #                "odmlDatatype": ""}

                for col_n in list(range(len(row))):
                    # using only columns with header
                    if col_n in header_title_order:
                        new_dic[header_title_order[col_n]] = row[col_n]

                # update path and remove section and property names
                new_dic['Path'] = new_dic['Path'] + ':' + new_dic['PropertyName']
                new_dic.pop('PropertyName')
                new_dic.pop('SectionName')

                # convert to python datatypes
                dtype = new_dic['odmlDatatype']
                value = new_dic['Value']
                new_dic['Value'] = [self.odtypes.to_odml_value(value, dtype)]

                if (new_dic['Path'].split(':')[0] == ''
                    or current_dic['Path'].split(':')[0] == new_dic['Path'].split(':')[0]):
                    # it is not the start of a new section

                    if new_dic['Path'] == '' or (current_dic['Path'] == new_dic['Path']):
                        # old section, old property
                        # for key in self._SECTION_INF:
                        #     current_dic[key] = old_dic[key]
                        # for key in self._PROPERTY_INF:
                        #     current_dic[key] = old_dic[key]
                        current_dic['Value'].extend(new_dic['Value'])
                    else:
                        # old section, new property
                        for key in self._PROPERTY_INF:
                            current_dic[key] = new_dic[key]
                        is_new_property = True
                else:
                    is_new_property = True

                if is_new_property and row_id > 0:
                    self._odmldict.append(copy.deepcopy(current_dic))
                    current_dic = new_dic

            # copy final property
            if row_id == 0:
                self._odmldict.append(copy.deepcopy(new_dic))
            else:
                self._odmldict.append(copy.deepcopy(current_dic))
        self._odmldict = self._sort_odmldict(self._odmldict)

    def change_header_titles(self, **kwargs):
        """
        Function to change the Name of a column in your table. Be careful with
        this function if you want to convert the table back to an odml.


        :param Path: Name of the 'Path'-Column in the table
        :param SectionName: Name of the 'Section Name'-Column in the table
        :param SectionType: Name of the 'Section Type'-Column in the table
        :param SectionDefinition: Name of the 'Section Definition'-Column in
            the table
        :param ProgertyName: Name of the 'Property Name'-Column in the table
        :param PropertyDefinition: Name of the 'Property Definition'-Column in
            the table
        :param Value: Name of the 'Value'-Column in the table
        :param DataUnit: Name of the 'Data Unit'-Column in the table
        :param DataUncertainty: Name of the 'Data Uncertainty'-Column in the
            table
        :param odmlDatatype: Name of the 'odML Data Type'-Column in the table
        :type Path: string, optional
        :type SectionName: string, optional
        :type SectionType: string, optional
        :type SectionDefinition: string, optional
        :type ProgertyName: string, optional
        :type PropertyDefinition: string, optional
        :type Value: string, optional
        :type DataUnit: string, optional
        :type DataUncertainty: string, optional
        :type odmlDatatype: string, optional

        """

        for k in kwargs:
            if k in self._header_titles:
                self._header_titles[k] = kwargs[k]
            else:
                errmsg = "{0} is not in the header_title-dictionary".format(k)
                raise ValueError(errmsg)
                # TODO: better exception

    def change_header(self, **kwargs):
        """
        Function to change the header of the table.

        The keywordarguments of the function are the possible columns you can
        include into your table; they are listed below, you can also check the
        possible options bei looking at the keys of the header_titles
        dictionary. They take the number of their position in the table,
        starting from left with 1.
        The default-header is ['Path', 'Property Name', 'Value', 'odML Data
        Type']. These are the columns you need to be able to convert your table
        back to an odml-file. Important: You can create tables wich dont
        contain any of those four, but they cant be converted back to odml.

        :param Path: Position of the 'Path'-Column in the table.
        :param SectionName: Position of the 'Section Name'-Column in the table
        :param SectionType: Position of the 'Section Type'-Column in the table
        :param SectionDefinition: Position of the 'Section Definition'-Column
            in the table
        :param PropertyName: Position of the 'Property Name'-Column in the
            table
        :param PropertyDefinition: Position of the 'Property Definition'-Column
            in the table
        :param Value: Position of the 'Value'-Column in the table
        :param DataUnit: Position of the 'Data Unit'-Column in the table
        :param DataUncertainty: Position of the 'Data Uncertainty'-Column in
            the table
        :param odmlDatatype: Position of the 'odML Data Type'-Column in the
            table
        :type Path: int, optional
        :type SectionName: int, optional
        :type SectionType: int, optional
        :type SectionDefinition: int, optional
        :type PropertyName: int, optional
        :type PropertyDefinition: int, optional
        :type Value: int, optional
        :type DataUnit: int, optional
        :type DataUncertainty: int, optional
        :type odmlDatatype: int, optional

        :Example:

            mytable.change_header(Path=1, Value=3, odmlDataType=2)
                => outcoming header: ['Path', 'odML Data Type', 'Value']

        """

        # sortieren nach values
        keys_sorted = sorted(kwargs, key=kwargs.get)

        # check if first element is in range
        if kwargs[keys_sorted[0]] <= 0:
            errmsg = ("Your smallest argument is {}, but the columns start" +
                      " at 1").format(kwargs[keys_sorted[0]])
            raise ValueError(errmsg)
            # TODO: better Exception

        max_col = kwargs[keys_sorted[-1]]

        # initialize header with enough elements
        header = max_col * [None]

        if keys_sorted[0] in self._header_titles:
            header[kwargs[keys_sorted[0]] - 1] = keys_sorted[0]
        else:
            raise KeyError(keys_sorted[0], "not in header_titles")
            # TODO: better Exception

        # check if there are two keys with the same value
        for index, key in enumerate(keys_sorted[1:]):
            if kwargs[keys_sorted[index]] == kwargs[keys_sorted[index - 1]]:
                errmsg = "The keys {0} and {1} both have the value {2}" \
                    .format(keys_sorted[index - 1],
                            keys_sorted[index],
                            kwargs[keys_sorted[index]])
                raise KeyError(errmsg)
                # TODO: better exception
            else:
                if key in self._header_titles:
                    header[kwargs[key] - 1] = key
                else:
                    raise KeyError(key, "not in header_titles")
                    # TODO: better Exception

        self._header = header

    def consistency_check(self):
        """
        check odmldict for consistency regarding dtypes to ensure that data
        can be loaded again.
        """
        if self._odmldict != None:
            for property_dict in self._odmldict:
                if property_dict[
                    'odmlDatatype'] not in self.odtypes.valid_dtypes:
                    raise TypeError(
                            'Non valid dtype "{0}" in odmldict. Valid types are {1}'
                            ''.format(property_dict['odmlDatatype'], self.odtypes.valid_dtypes))

    def _filter(self, filter_func):
        """
        remove odmldict entries which do not match filter_func.
        """
        # inflate odmldict for filtering
        for dic in self._odmldict:
            sec_path, dic['PropertyName'] = dic['Path'].split(':')
            dic['SectionName'] = sec_path.split('/')[-1]

        new_odmldict = [d for d in self._odmldict if filter_func(d)]
        deleted_properties = [d for d in self._odmldict if not filter_func(d)]

        self._odmldict = new_odmldict
        return new_odmldict, deleted_properties

    def filter(self, mode='and', invert=False, recursive=False,
               comparison_func=lambda x, y: x == y, **kwargs):
        """
        filters odml properties according to provided kwargs.

        :param mode: Possible values: 'and', 'or'. For 'and' all keyword
                arguments must be satisfied for a property to be selected. For 'or'
                only one of the keyword arguments must be satisfied for the property
                to be selected. Default: 'and'
        :param invert: Inverts filter function. Previously accepted properties
                are rejected and the other way round. Default: False
        :param recursive: Delete also properties attached to subsections of the
                mother section and therefore complete branch
        :param comparison_func: Function used to compare dictionary entry to
               keyword. Eg. 'lambda x,y: x.startswith(y)' in case of strings or
               'lambda x,y: x in y' in case of multiple permitted values.
               Default: lambda x,y: x==y
        :param kwargs: keywords and values used for filtering
        :return: None
        """
        if not kwargs:
            raise ValueError('No filter keywords provided for property filtering.')
        if mode not in ['and', 'or']:
            raise ValueError('Invalid operation mode "%s". Accepted values are "and", "or".'
                             '' % (mode))

        def filter_func(dict_prop):
            keep_property = False
            for filter_key, filter_value in iteritems(kwargs):
                if filter_key not in dict_prop:
                    raise ValueError('Key "%s" is missing in property dictionary %s'
                                     '' % (filter_key, dict_prop))

                if comparison_func(dict_prop[filter_key], filter_value):
                    keep_property = True
                else:
                    keep_property = False

                if mode == 'or' and keep_property:
                    break
                if mode == 'and' and not keep_property:
                    break

            if invert:
                keep_property = not keep_property

            return keep_property

        _, del_props = self._filter(filter_func=filter_func)

        if recursive and len(del_props) > 0:
            for del_prop in del_props:
                self.filter(invert=True, recursive=True,
                            comparison_func=lambda x, y: x.startswith(y),
                            Path=del_prop['Path'])

    def merge(self, odmltable, mode='overwrite'):
        """
        Merge odmltable into current odmltable.
        :param odmltable: OdmlTable object or Odml document object
        :return:
        """
        if hasattr(odmltable, 'convert2odml'):
            doc2 = odmltable.convert2odml()
        else:
            # assuming odmltable is already an odml document
            doc2 = odmltable
        doc1 = self.convert2odml()

        # TODO: include value merge in section merge
        self._merge_odml_sections(doc1,doc2)
        self._merge_odml_values(doc1, doc2, mode=mode)

        # TODO: What should happen to the document properties?
        """
        'author'
        'date'
        'version'
        'repository'
        """

        # TODO: Check what happens to original odmldict...
        self.load_from_odmldoc(doc1)

    def _merge_odml_sections(self, sec1, sec2, mode='overwrite'):
        """
        Merging subsections of odml sections
        """
        # TODO: Reintroduce mode keyword
        # if mode not in ['strict', 'overwrite']:
        #     raise ValueError('Merge mode "%s" does not exist. '
        #                      'Valid modes are %s' % ((mode, ['strict',
        #                                                      'overwrite'])))

        for childsec2 in sec2.sections:
            sec_name = childsec2.name
            if not sec_name in sec1.sections:
                sec1.append(childsec2)
            else:
                self._merge_odml_sections(sec1[sec_name], childsec2)

            # merge properties
            if hasattr(sec1, 'properties') and hasattr(sec2, 'properties'):
                for prop2 in sec2.properties:
                    if prop2.name not in sec1.properties:
                        sec1.properties.append(prop2)


    # TODO adjust function to new value model
    def _merge_odml_values(self, doc1, doc2, mode='overwrite'):
        """
        Merging values of odml documents, which contain the IDENTICAL
        sections and properties and only differ in the odml values
        """
        if mode not in ['strict', 'overwrite']:
            raise ValueError('Merge mode "%s" does not exist. '
                             'Valid modes are %s' % ((mode, ['strict',
                                                             'overwrite'])))

        for prop2 in doc2.iterproperties():
            path = prop2.get_path()
            prop1 = doc1.get_property_by_path(path)

            if mode == 'strict':
                if (len(prop1.value) != 1) or \
                        (prop1.value[0] not in
                             list(self.odtypes._basedtypes.values())):
                    raise ValueError('OdML property %s already contains '
                                     'non-default values %s' % (prop1.name,
                                                                prop1.value))

            if mode in ['overwrite', 'strict']:
                # removing old values, but keeping first element, because a
                # property needs to contain at least one value at any time
                if prop1 != prop2:  # properties can be identical, when section
                    #  was copied. Then no value transfer is necessary.
                    for val in prop1.value[1:]:
                        prop1.remove(val)
                    # adding new values (which is at least one, see comment
                    # above)
                    for val in prop2.value:
                        prop1.value.append(val)
                    prop1.remove(prop1.value[0])

    def write2file(self, save_to):
        """
        write the table to the specific file
        """
        raise NotImplementedError()

        self.consistency_check()

    def convert2odml(self):
        """
        Generates odml representation of odmldict and return it as odml
        document.
        :return:
        """
        doc = odml.Document()
        oldpath = ''
        parent = ''

        self.consistency_check()

        for dic in self._odmldict:
            # build property object
            prop_name = self._split_path(dic)[-1]
            prop = odml.Property(name=prop_name,
                                 value=dic['Value'],
                                 dtype=dic['odmlDatatype'])

            if 'PropertyDefinition' in self._header:
                prop.definition = dic['PropertyDefinition']
            if 'DataUnit' in self._header:
                prop.unit = dic['DataUnit']
            if 'DataUncertainty' in self._header:
                prop.uncertainty = dic['DataUncertainty']

            sec_path = dic['Path'].split(':')[0]
            current_sec = doc
            # build section tree for this property
            for sec_pathlet in sec_path.split('/')[1:]:
                # append new section if not present yet
                if sec_pathlet not in current_sec.sections:
                    current_sec.append(odml.Section(name=sec_pathlet))
                current_sec = current_sec[sec_pathlet]

            if 'SectionType' in self._header:
                current_sec.type = dic['SectionType']
            if 'SectionDefinition' in self._header:
                current_sec.definition = dic['SectionDefinition']

            current_sec.append(prop)

        return doc

    def write2odml(self, save_to):
        """
        writes the loaded odmldict (e.g. from an csv-file) to an odml-file
        """
        doc = self.convert2odml()
        odml.tools.xmlparser.XMLWriter(doc).write_file(save_to)


class OdmlDtypes(object):
    """
    Class to handle odml data types, synonyms and default values.

    :param basedtypes_dict: Dictionary containing additional basedtypes to
    use as keys and default values as values.
            Default: None
    :param synonyms_dict: Dictionary containing additional synonyms to use as
    keys and basedtypes to associate as values.
            Default: None
    :return: None
    """

    default_basedtypes = {'int': -1,
                          'float': -1.0,
                          'bool': False,
                          'datetime': datetime.datetime(1900, 11, 11, 00, 00,
                                                        00),
                          'datetime.date': datetime.datetime(1900, 11,
                                                             11).date(),
                          'datetime.time': datetime.datetime(1900, 11, 11, 00,
                                                             00, 00).time(),
                          'str': '-',
                          'url': 'file://-'}
    default_synonyms = {'boolean': 'bool', 'binary': 'bool',
                        'date': 'datetime.date', 'time': 'datetime.time',
                        'integer': 'int', 'string': 'str', 'text': 'str',
                        'person': 'str'}

    def __init__(self, basedtypes_dict=None, synonyms_dict=None):
        self._basedtypes = self.default_basedtypes.copy()
        self._synonyms = self.default_synonyms.copy()
        self._validDtypes = None

        # update default values with used defined defaults
        if basedtypes_dict is not None:
            self._basedtypes.update(basedtypes_dict)
        if synonyms_dict is not None:
            self._synonyms.update(synonyms_dict)

    @property
    def valid_dtypes(self):
        # if not done yet: generate validDtype list with unique entries
        if self._validDtypes == None:
            validDtypes = list(self._basedtypes)
            for syn in list(self._synonyms):
                if syn not in validDtypes:
                    validDtypes.append(syn)
            self._validDtypes = validDtypes

        return self._validDtypes

    @property
    def synonyms(self):
        return self._synonyms

    def add_synonym(self, basedtype, synonym):
        """
        Setting user specific default synonyms
        :param basedtype: Accepted basedtype of OdmlDtypes or None. None
        delete already existing synonym
        :param synonym: Synonym to be connected to basedtype
        :return: None
        """
        if basedtype not in self._basedtypes:
            if basedtype is None and synonym in self._synonyms:
                self._synonyms.pop(synonym)
            else:
                raise ValueError(
                        'Can not add synonym "%s=%s". %s is not a base dtype.'
                        'Valid basedtypes are %s.' % (
                            basedtype, synonym, basedtype, self.basedtypes))

        elif synonym is None or synonym == '':
            raise ValueError('"%s" is not a valid synonym.' % synonym)
        else:
            self._synonyms.update({synonym: basedtype})

    @property
    def basedtypes(self):
        return list(self._basedtypes)

    def add_basedtypes(self, basedtype, default_value):
        if basedtype in self._basedtypes:
            raise ValueError('Basedtype "%s" already exists. Can not be added. '
                             'To customize the default value use '
                             '"customize_default".')
        else:
            self._basedtypes.update({basedtype: default_value})

    @property
    def default_values(self):
        def_values = self._basedtypes.copy()
        for syn, base in iteritems(self._synonyms):
            def_values[syn] = self._basedtypes[base]
        return def_values

    def default_value(self, basedtype):
        if basedtype in self.default_values:
            return self.default_values[basedtype]
        else:
            raise ValueError(
                    '"%s" is not a basedtype. Valid basedtypes are %s' % (
                        basedtype, self.basedtypes))

    def set_default_value(self, basedtype, default_value):
        if basedtype in self.basedtypes:
            self._basedtypes[basedtype] = default_value
        else:
            raise ValueError('Can not set default value for basedtype "%s". '
                             'This is not a basedtype. Valid basedtypes are '
                             '%s' % (
                                 basedtype, self.basedtypes))

    def to_odml_value(self, value, dtype):
        # return default value of dtype if value is empty
        if value == '':
            return self.default_value(dtype)

        if dtype in self._synonyms:
            dtype = self._synonyms[dtype]

        if dtype == 'datetime':
            if isinstance(value, datetime.datetime):
                result = value
            else:
                try:
                    result = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except TypeError:
                    result = datetime.datetime(*value)
        elif dtype == 'datetime.date':
            if isinstance(value, datetime.date):
                result = value
            else:
                try:
                    result = datetime.datetime.strptime(value, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        result = datetime.datetime.strptime(value, '%d-%m-%Y').date()
                    except ValueError:
                        raise ValueError(
                                'The value "%s" can not be converted to a date as '
                                'it has not format yyyy-mm-dd or dd-mm-yyyy' % value)
                except TypeError:
                    result = datetime.datetime(*value).date()
        elif dtype == 'datetime.time':
            if isinstance(value, datetime.time):
                result = value
            else:
                try:
                    result = datetime.datetime.strptime(value, '%H:%M:%S').time()
                except TypeError:
                    try:
                        result = datetime.datetime(*value).time()
                    except ValueError:
                        result = datetime.time(*value[-3:])

        elif dtype == 'url':
            result = str(value)

        elif dtype in self._basedtypes:
            try:
                result = eval('%s(%s)' % (dtype, value))
            except Exception:
                result = eval('%s("%s")' % (dtype, value))
        else:
            raise TypeError('Unknown dtype {0}'.format(dtype))

        return result
