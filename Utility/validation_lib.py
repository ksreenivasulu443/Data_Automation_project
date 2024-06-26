from pyspark.sql.functions import abs, count, when, isnan, isnull, col, trim
import datetime
import json
import sys

import pandas as pd

from pyspark.sql import SQLContext, SparkSession
from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql.functions import explode_outer, concat, col, \
    trim, to_date, lpad, lit, count, max, min, explode
from pyspark.sql.types import IntegerType
import os
import smtplib
from itertools import chain
from string import Template



def count_check(sourceDF, targetDF,Out,row):
    print("*" * 50)
    print("count validation started".center(40))
    print("*" * 50)
    source_count = sourceDF.count()
    target_count = targetDF.count()
    diff = (source_count - target_count).__abs__()
    if source_count == target_count:
        print("Source count and target count is matching and count is", source_count)
        write_output(row['batch_id'], "count_check", row["source"], row["target"], source_count, target_count, 0,
                     row['key_col_list'], "pass",Out,row['source_type'],row['target_type'])
    else:
        print("Source count and taget count is not matching and difference is", source_count - target_count)
        write_output(row['batch_id'], "count_check", row["source"], row["target"], source_count, target_count, diff,
                     row['key_col_list'], "fail",Out,row['source_type'],row['target_type'])
    print("*" * 40)
    print("count validation completed".center(40))
    print("*" * 40)


def duplicate_check(dataframe, key_column: list, Out, row):
    print("*" * 50)
    print("duplicate validation started ".center(50))
    print("*" * 50)
    key_column = key_column.split(",")
    dup_df = dataframe.groupBy(key_column).count().filter('count>1')
    target_count = dataframe.count()
    failed = dup_df.count()
    if dup_df.count() > 0:
        print("Duplicates present")
        dup_df.show(10)
        write_output(row['batch_id'], "duplicate_check", row['source'], row["target"], "NOT APP", target_count, failed, row['key_col_list'],
                     "fail", Out,row['source_type'],row['target_type'])
    else:
        print("No duplicates")
        write_output(row['batch_id'], "duplicate_check", row['source'], row["target"], "NOT APP", target_count, failed, row['key_col_list'],
                     "pass", Out,row['source_type'],row['target_type'])
    print("*" * 50)
    print("duplicate validation completed ".center(50))
    print("*" * 50)


def uniqueness_check(dataframe, unique_column: list, Out, row):
    print("*" * 50)
    print("uniqueness validation started ".center(50))
    print("*" * 50)
    target_count = dataframe.count()
    unique_column = unique_column.split(",")
    for column in unique_column:
        dup_df = dataframe.groupBy(column).count().filter('count>1')
        failed = dup_df.count()
        if dup_df.count() > 0:
            print(f"{column} columns has duplicate")
            dup_df.show(10)
            write_output(row['batch_id'], "uniqueness_check", row['source'], row["target"], "NOT APP", target_count, failed, column, "fail", Out,row['source_type'],row['target_type'])

        else:
            print("All records has unique records")
            write_output(row['batch_id'], "uniqueness_check", row['source'], row["target"], "NOT APP", target_count, failed, column, "pass", Out,row['source_type'],row['target_type'])
    print("*" * 50)
    print("uniqueness validation completed ".center(50))
    print("*" * 50)


def null_value_check(dataframe, Null_columns, Out, row):
    print("*" * 50)
    print("null value check validation started ".center(50))
    print("*" * 50)
    target_count = dataframe.count()
    Null_columns = Null_columns.split(",")
    for column in Null_columns:
        Null_df = dataframe.select(count(when(col(column).contains('None') |
                                              col(column).contains('NULL') |
                                              col(column).contains('Null') |
                                              (col(column) == '') |
                                              col(column).isNull() |
                                              isnan(column), column
                                              )).alias("Null_value_count"))
        # dataframe.createOrReplaceTempView("dataframe")
        # Null_df = spark.sql(f"select count(*) source_cnt from dataframe where {column} is null")
        failed = Null_df.collect()[0][0]

        if failed > 0:
            print(f"{column} columns has Null values")
            write_output(row['batch_id'], "null_value_check", row['source'], row["target"], "NOT APP", target_count, failed, column, "fail", Out,row['source_type'],row['target_type'])

        else:
            print("No null records present")
            write_output(row['batch_id'], "null_value_check", row['source'], row["target"], "NOT APP", target_count, 0, column, "pass", Out,row['source_type'],row['target_type'])
    print("*" * 50)
    print("null value check validation completed ".center(50))
    print("*" * 50)


def records_present_only_in_target(source, target, keyList: list, Out, row):
    print("*" * 50)
    print("records_present_only_in_target validation started ".center(50))
    print("*" * 50)
    columns = keyList
    keyList = keyList.split(",")
    srctemp = source.select(keyList).groupBy(keyList).count().withColumnRenamed("count", "SourceCount")
    tartemp = target.select(keyList).groupBy(keyList).count().withColumnRenamed("count", "TargetCount")
    count_compare = srctemp.join(tartemp, keyList, how='full_outer')
    failed = count_compare.filter("SourceCount is null").count()
    print("Key column record present in target but not in Source :" + str(failed))
    source_count = source.count()
    target_count = target.count()
    if failed > 0:
        count_compare.filter("SourceCount is null").show()
        write_output(row['batch_id'], "records_present_only_in_target", row["source"], row["target"], source_count, target_count,
                     failed, columns, "fail", Out,row['source_type'],row['target_type'])

    else:
        print("No extra records present in source")
        write_output(row['batch_id'], "records_present_only_in_target", row["source"], row["target"], source_count, target_count, 0,
                     columns, "pass", Out,row['source_type'],row['target_type'])
    print("*" * 50)
    print("records_present_only_in_target validation completed ".center(50))
    print("*" * 50)


def records_present_only_in_source(source, target, keyList, Out, row):
    print("*" * 50)
    print("records_present_only_in_source validation has started ".center(50))
    print("*" * 50)
    columns = keyList
    keyList = keyList.split(",")
    srctemp = source.select(keyList).groupBy(keyList).count().withColumnRenamed("count", "SourceCount")
    tartemp = target.select(keyList).groupBy(keyList).count().withColumnRenamed("count", "TargetCount")
    count_compare = srctemp.join(tartemp, keyList, how='full_outer')
    failed = count_compare.filter("TargetCount is null").count()
    source_count = source.count()
    target_count = target.count()
    print("Key column record present in Source but not in target :" + str(failed))
    if failed > 0:
        count_compare.filter("TargetCount is null").show()
        write_output(row['batch_id'], "records_present_only_in_source", row["source"], row["target"], source_count, target_count,
                     failed, columns, "fail", Out,row['source_type'],row['target_type'])

    else:
        print("No extra records present")
        write_output(row['batch_id'], "records_present_only_in_source", row["source"], row["target"], source_count, target_count, 0,
                     columns, "pass", Out,row['source_type'],row['target_type'])
    print("*" * 50)
    print("records_present_only_in_source validation completed ".center(50))
    print("*" * 50)


def data_compare(source, target, keycolumn, Out,row):
    print("*" * 50)
    print("Data compare validation has started ".center(50))
    print("*" * 50)
    #key_col_comma_sep=keycolumn

    keycolumn = keycolumn.split(",")
    col_values_as_strings = ["'" + str(x).lower() + "'" for x in keycolumn]

    # Concatenate the values into a single comma-separated string
    #comma_separated_string = ','.join(col_values_as_strings)

    keycolumn = [i.lower() for i in keycolumn]
    print(keycolumn)
    columnList = source.columns
    print(columnList)
    smt = source.exceptAll(target).withColumn("datafrom", lit("source"))
    tms = target.exceptAll(source).withColumn("datafrom", lit("target"))
    failed = smt.union(tms)
    num_fail_count=failed.count()
    source_count = source.count()
    target_count = target.count()
    columns  = ','.join(keycolumn)
#    print("columns", comma_separated_string)
    if num_fail_count > 0:
        write_output(row['batch_id'], "data_compare", row["source"], row["target"], source_count, target_count,
                     num_fail_count, columns, "fail", Out,row['source_type'],row['target_type'])

    else:
        write_output(row['batch_id'], "data_compare", row["source"], row["target"], source_count, target_count,
                     0, columns, "fail", Out,row['source_type'],row['target_type'])

    failed.show(5)
    #failed_records = failed.select(keycolumn).withColumn("hash_key", concat(comma_separated_string)).collect()
    #print(failed_records)
    #source = source.withColumn('has_key', concat(columns)).filter(f'hash_key in {failed_records}').drop('hash_key')
    #source.show()
    #target = target.withColumn('has_key', concat(key_col_comma_sep)).filter(f'hash_key in {failed_records}').drop(
    #    'hash_key')
    if failed.count()>0:
        for column in columnList:
            print(column.lower())
            if column.lower() not in keycolumn:
                keycolumn.append(column)
                temp_source = source.select(keycolumn).withColumnRenamed(column, "source_" + column)
                temp_target = target.select(keycolumn).withColumnRenamed(column, "target_" + column)
                keycolumn.remove(column)
                temp_join = temp_source.join(temp_target, keycolumn, how='full_outer')
                temp_join.withColumn("comparison", when(col('source_' + column) == col("target_" + column),
                                                        "True").otherwise("False")).filter("comparison == False").show()
    print("*" * 50)
    print("Data compare validation has completed ".center(50))
    print("*" * 50)


def compare(source, target, countQA, keyList, Out):
    sourceDaraFrame = source
    targetDataFrame = target
    for colname in sourceDaraFrame.columns:
        sourceDaraFrame = sourceDaraFrame.withColumn(colname, trim(col(colname)))

    for colname in targetDataFrame.columns:
        targetDataFrame = targetDataFrame.withColumn(colname, trim(col(colname)))
    match_stats = []
    sampleCount = 10
    columnList = sourceDaraFrame.columns
    subStringMap = {}
    Summary = {"Column": [], "Total": [], "Matchcount": [], "Mismatchcount": [], "Mismatchcountper": []}
    report = "Column_Name" + "\t" + "Match_count" + "\t" + "mismatch_count" + "\t" + "Mismatch_percentage"
    for column in columnList:
        try:
            subString = subStringMap.__getitem__(column)
        except:
            subString = ''
        if column not in keyList:
            matchcount, a, b = run_compare_for_column(keyList, column, sourceDaraFrame, targetDataFrame, sampleCount,
                                                      subString)
            mismatchcount = countQA - matchcount
            mismatchcountper = mismatchcount * 100 / float(countQA)
            Summary['Column'].append(column)
            Summary['Total'].append(countQA)
            Summary['Matchcount'].append(matchcount)
            Summary['Mismatchcount'].append(mismatchcount)
            Summary['Mismatchcountper'].append(mismatchcountper)
    Summary = pd.DataFrame(Summary)
    if Summary.Mismatchcount.sum() > 0:
        write_output(5, "Datavalidation", countQA, countQA, "FAIL", Summary.Mismatchcount.sum(), Out)
    else:
        write_output(5, "Datavalidation", countQA, countQA, "PASS", 0, Out)
    return Summary


def get_dataset(keyList, keyDict, dataframe, one_more_value):
    var_dict = {}
    condition = ''
    # print keyDict
    i = 0
    for key, val in keyDict.items():
        if i > 0:
            condition = str(key) + " == '" + str(val) + "' and " + condition
            # print("Condition inside if " , condition)
        else:
            condition = str(key) + " == '" + str(val) + "'"
            # print("Condition inside elif " ,condition)
        i = i + 1
    var_dict.__setitem__('condition', condition)
    var_dict.__setitem__('dataframe', [k for k, v in locals().items() if v == dataframe][0])
    command = '''$dataframe.filter("$condition").show(20, False)'''
    # print(command)
    command = Template(command).substitute(var_dict)
    # print(command)
    eval(command)
    print("\n\n")


def run_compare_for_column(keyList, column, sourceDataFrame, targetDataFrame, sampleCount, substring, tolerance=None):
    print("Validation for column - " + column)
    var_dict = {}
    var_dict.__setitem__('keyList', keyList)
    var_dict.__setitem__('column', column)
    var_dict.__setitem__('sourceDataFrame', [k for k, v in locals().items() if v == sourceDataFrame][0])
    var_dict.__setitem__('targetDataFrame', [k for k, v in locals().items() if v == targetDataFrame][0])
    var_dict.__setitem__('substring', substring)
    var_dict.__setitem__('samplecount', sampleCount)
    var_dict.__setitem__('tolerance', tolerance)
    if tolerance is None:
        command = '''$sourceDataFrame.join($targetDataFrame, $keyList, how="fullouter").filter(((
        $sourceDataFrame.$column.isNotNull()) & ($targetDataFrame.$column.isNotNull()) | (
        $sourceDataFrame.$column.isNull()) & ($targetDataFrame.$column.isNull()))).select("''' + (
            '" , "').join(keyList) + '''", $sourceDataFrame.$column, $targetDataFrame.$column,
         F.when(trim($sourceDataFrame.$column$substring) == trim($targetDataFrame.$column$substring),"True").
         otherwise("False").alias('Diff_$column')).filter("Diff_$column == False").count()'''

    else:
        command = '''$sourceDataFrame.join($targetDataFrame, $keyList, how="fullouter").filter(((
        $sourceDataFrame.$column.isNotNull()) & ($targetDataFrame.$column.isNotNull()) | (
        $sourceDataFrame.$column.isNull()) & ($targetDataFrame.$column.isNull()))).select("''' + (
            '" , "').join(keyList) + '''", $sourceDataFrame.$column, $targetDataFrame.$column,
         F.when(trim($sourceDataFrame.$column$substring) == trim($targetDataFrame.$column$substring),"True").
         otherwise("False").alias('Diff_$column')).count()'''
    command = Template(command).substitute(var_dict)
    count = eval(command)
    Mismatchcount = count
    print("Data is not matching for " + str(Mismatchcount) + " records" + "\n")
    if count > 0:
        if tolerance is None:
            command = '''$sourceDataFrame.join($targetDataFrame, $keyList, how="fullouter").filter(((
            $sourceDataFrame.$column.isNotNull()) & ($targetDataFrame.$column.isNotNull()) | (
            $sourceDataFrame.$column.isNull()) & ($targetDataFrame.$column.isNull()))).select("''' + (
                '" , "').join(keyList) + '''", $sourceDataFrame.$column, $targetDataFrame.$column,
         F.when(trim($sourceDataFrame.$column$substring) == trim($targetDataFrame.$column$substring),"True").
         otherwise("False").alias('Diff_$column')).filter("Diff_$column == False")'''
        else:
            command = '''$sourceDataFrame.join($targetDataFrame, $keyList, how="fullouter").filter(((
            $sourceDataFrame.$column.isNotNull()) & ($targetDataFrame.$column.isNotNull()) | (
            $sourceDataFrame.$column.isNull()) & ($targetDataFrame.$column.isNull()))).select("''' + (
                '" , "').join(keyList) + '''", $sourceDataFrame.$column, $targetDataFrame.$column, F.when(trim(
                $sourceDataFrame.$column$substring) == trim($targetDataFrame.$column$substring),"True"). otherwise(
                "False").alias('Diff_$column))'''
        command = Template(command).substitute(var_dict)
        sampleData = eval(command)
        # sampleData.columns=[[sampleData.columns[0],'Source','Target','dfii']]
        sampleData.show(10)
        # sampleData.show(sampleCount, False)
        print("Sample mismatch records " + ",".join(keyList))
        print('-----------------------------------------------')
        keyListdata = sampleData.select(keyList).first().asDict()
        print('Source dataFrame details')
        get_dataset(keyList, keyListdata, sourceDataFrame, 'abc')
        print("Target dataFrame details")
        get_dataset(keyList, keyListdata, targetDataFrame)

    if tolerance is None:
        command = '''$sourceDataFrame.join($targetDataFrame, $keyList, how="fullouter").filter(((
        $sourceDataFrame.$column.isNotNull()) & ($targetDataFrame.$column.isNotNull()) | (
        $sourceDataFrame.$column.isNull()) & ($targetDataFrame.$column.isNull()))).select("''' + (
            '" , "').join(keyList) + '''", $sourceDataFrame.$column, $targetDataFrame.$column,F.when(trim(
            $sourceDataFrame.$column$substring) == trim($targetDataFrame.$column$substring),"True"). otherwise(
            "False").alias('Diff_$column')).filter("Diff_$column == True").count()'''
        command = Template(command).substitute(var_dict)
        # print(command)
        count = eval(command)
        matched_count = count
        # print("Data is not exactly matching for " + str(matched_count))
    return matched_count, Mismatchcount, matched_count + Mismatchcount


def write_output(TC_ID, validation_Type, source, target, Number_of_source_Records, Number_of_target_Records,
                 Number_of_failed_Records, column, Status, Out,source_type=None,target_type=None):
    Out["batch_id"].append(TC_ID)
    Out["Source_name"].append(source)
    Out["target_name"].append(target)
    Out["column"].append(column)
    Out["validation_Type"].append(validation_Type)
    Out["Number_of_source_Records"].append(Number_of_source_Records)
    Out["Number_of_target_Records"].append(Number_of_target_Records)
    Out["Status"].append(Status)
    Out["Number_of_failed_Records"].append(Number_of_failed_Records)
    Out["source_type"].append(source_type)
    Out["target_type"].append(target_type)



from pyspark.sql.types import *
from pyspark.sql.functions import *


def flatten(df):
    # compute Complex Fields (Lists and Structs) in Schema
    complex_fields = dict([(field.name, field.dataType)
                           for field in df.schema.fields
                           if type(field.dataType) == ArrayType or type(field.dataType) == StructType])
    while len(complex_fields) != 0:
        col_name = list(complex_fields.keys())[0]
        print("Processing :" + col_name + " Type : " + str(type(complex_fields[col_name])))

        # if StructType then convert all sub element to columns.
        # i.e. flatten structs
        if type(complex_fields[col_name]) == StructType:
            expanded = [col(col_name + '.' + k).alias(col_name + '_' + k) for k in
                        [n.name for n in complex_fields[col_name]]]
            df = df.select("*", *expanded).drop(col_name)

        # if ArrayType then add the Array Elements as Rows using the explode function
        # i.e. explode Arrays
        elif type(complex_fields[col_name]) == ArrayType:
            df = df.withColumn(col_name, explode_outer(col_name))

        # recompute remaining Complex Fields in Schema
        complex_fields = dict([(field.name, field.dataType)
                               for field in df.schema.fields
                               if type(field.dataType) == ArrayType or type(field.dataType) == StructType])
    return df

def send_email(df):
    pass
