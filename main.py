"""This file will be starting point for automation execution"""
import os
import sys

from Utility.files_read_lib import *
from Utility.validation_lib import *
import pandas as pd

from Utility.write_db_file_lib import write_summary_table
from pyspark.sql import SparkSession
from pyspark.sql.functions import collect_set
import datetime
import openpyxl

batch_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")



os.environ.setdefault("project_path", os.getcwd())
project_path = os.environ.get("project_path")


# jar_path = pkg_resources.resource_filename('jars', 'postgresql-42.2.5.jar')
postgre_jar = project_path + "/jars/postgresql-42.2.5.jar"
snow_jar = project_path + "/jars/snowflake-jdbc-3.14.3.jar"
oracle_jar = project_path + "/jars/ojdbc11.jar"

jar_path = postgre_jar+','+snow_jar + ','+oracle_jar
spark = SparkSession.builder.master("local") \
    .appName("test") \
    .config("spark.jars", jar_path) \
    .config("spark.driver.extraClassPath", jar_path) \
    .config("spark.executor.extraClassPath", jar_path) \
    .getOrCreate()

cwd = os.getcwd()
# user = os.environ.get('USER')
# print(user)
# result_local_file = cwd+'\logfile.txt'
# print("result_local_file",result_local_file)

# if os.path.exists(result_local_file):
#     os.remove(result_local_file)

# file = open(result_local_file, 'a')
# original = sys.stdout
# sys.stdout = file

# template_path = pkg_resources.resource_filename("Config", "Master_Test_Template.xlsx")
template_path = project_path + '/Config/Master_Test_Template.xlsx'
print(template_path)
Test_cases = pd.read_excel(template_path)
run_test_case = Test_cases.loc[(Test_cases.execution_ind == 'Y')]
# print(run_test_case)
# print(run_test_case.columns)
df = spark.createDataFrame(run_test_case)
df.show()

validations = df.groupBy('source', 'source_type',
                         'source_db_name', 'schema_path', 'source_transformation_query_path', 'target',
                         'target_type', 'target_db_name', 'target_transformation_query_path',
                         'key_col_list', 'null_col_list', 'unique_col_list').agg(
    collect_set('validation_Type').alias('validation_Type'))

validations = validations.withColumn('batch_id',lit(batch_id))

validations.show(truncate=False)
#
validations = validations.collect()

Out = {"batch_id": [],
       "validation_Type": [],
       "Source_name": [],
       "target_name": [],
       "Number_of_source_Records": [],
       "Number_of_target_Records": [],
       "Number_of_failed_Records": [],
       "column": [],
       "Status": [],
       "source_type":[],
       "target_type":[]
       }
#
schema = ["batch_id",
          "validation_Type",
          "Source_name",
          "target_name",
          "Number_of_source_Records",
          "Number_of_target_Records",
          "Number_of_failed_Records",
          "column",
          "Status",
          "source_type",
          "target_type"]



for row in validations:
        print("*" * 80)
        print(row)
        print("Execution started for dataset ".center(80))
        print("*" * 80)
        if row['source_type'] == 'table':
            source = read_data(row,row['source_type'], row['source'], spark=spark, database=row['source_db_name'],
                                   sql_path=row['source_transformation_query_path'])
        else:
            source_path=fetch_source_file_path(row['source'])
            print("Source_path", source_path)
            source = read_data(row,row['source_type'], source_path, spark, schema=row['schema_path'])

        if row['target_type'] == 'table':
            print(row['target_type'], row['target'], row['target_db_name'])
            target = read_data(row,row['target_type'], row['target'], spark=spark, database=row['target_db_name'],
                                   sql_path=row['target_transformation_query_path'])
        elif row['target_type'] == 'snowflake':
            print(row,row['target_type'], row['target'], row['target_db_name'])
            target = read_data(row,row['target_type'], row['target'], spark=spark, database=row['target_db_name'],
                                   sql_path=row['target_transformation_query_path'])
        else:
            target_path = fetch_source_file_path(row['target'])
            target = read_data(row,row['target_type'], target_path, spark)

        source.show(n=2)
        target.show(n=2)
        for validation in row['validation_Type']:

            print(validation)
            if validation.strip().lower() == 'count_check':
                count_check(source, target, Out, row)
            elif validation == 'duplicate_check':
                duplicate_check(target, row['key_col_list'], Out, row)
            elif validation == 'null_value_check':
                null_value_check(target, row['null_col_list'], Out, row)
            elif validation == 'uniqueness_check':
                uniqueness_check(target, row['unique_col_list'], Out, row)
            elif validation == 'records_present_only_in_source':
                records_present_only_in_source(source, target, row['key_col_list'], Out, row)
            elif validation == 'records_present_only_in_target':
                records_present_only_in_target(source, target, row['key_col_list'], Out, row)
            elif validation == 'data_compare':
                data_compare(source, target, row['key_col_list'], Out,row)













print(Out)
summary = pd.DataFrame(Out)
summary.to_csv("summary.csv")

schema = StructType([
    StructField("batch_id", StringType(), True),
    StructField("validation_Type", StringType(), True),
    StructField("Source_name", StringType(), True),
    StructField("target_name", StringType(), True),
    StructField("Number_of_source_Records", StringType(), True),
    StructField("Number_of_target_Records", IntegerType(), True),
    StructField("Number_of_failed_Records", IntegerType(), True),
    StructField("column", StringType(), True),
    StructField("Status", StringType(), True),
    StructField("source_type", StringType(), True),
    StructField("target_type", StringType(), True)
])

# Convert Pandas DataFrame to Spark DataFrame
summary = spark.createDataFrame(summary, schema=schema)
#summary = spark.createDataFrame(summary)#.withColumn("fail_perce", col('Number_of_failed_Records')/col('Number_of_target_Records').cast('int'))
df2 = df.select('test_case_id','validation_Type','source','source_type','target','target_type')
df2.show()
summary.show()
df2 = df2.withColumnRenamed("source", "Source_name") \
         .withColumnRenamed("target","target_name")
df2.show()

summary= summary.join(df2, ['validation_Type','Source_name','target_name','source_type','target_type'], 'inner')

write_summary_table(summary)

