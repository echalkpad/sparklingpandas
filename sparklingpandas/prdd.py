"""Provide a way to work with panda data frames in Spark"""
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from sparklingpandas.utils import add_pyspark_path
from functools import reduce

add_pyspark_path()
from pyspark.join import python_join, python_left_outer_join, \
    python_right_outer_join, python_cogroup
from pyspark.rdd import RDD
from sparklingpandas.pstatcounter import PStatCounter
import pandas


class PRDD:

    """A Panda Resilient Distributed Dataset (PRDD), is an extension of the RDD."""

    def __init__(self, schemaRdd):
        """Please construct using a pcontext."""
        self._rdd = schemaRdd

    @classmethod
    def fromSchemaRDD(cls, schemaRdd):
        """Construct a PRDD from an SchemaRDD. No checking or validation occurs."""
        return PRDD(schemaRdd)
    @classmethod
    def fromDataFrameRDD(cls, rdd):
        """Construct a PRDD from an RDD of DataFrames. No checking or validation occurs."""
        result = PRDD(None)
        result.from_rdd_of_dataframes(rdd)
        return result

    def to_rdd_of_dataframes(self):
        """Convert a L{PRDD} into a RDD of DataFrames"""
        def _load_kv_partitions(partition):
            """Convert a partition where each row is key/value data."""
            partitionList = list(partition)
            if len(partitionList) > 0:
                return iter([
                    pandas.DataFrame(data=partitionList)
                ])
            else:
                return iter([])
        return self._rdd.mapPartitions(_load_kv_partitions)

    def __evil_apply_with_dataframes(self, func):
        """Convert the underlying SchmeaRDD to an RDD of DataFrames.
        apply the provide function and convert the result back.
        This is hella slow."""
        source_rdd = self.to_rdd_of_dataframes()
        result_rdd = func(source_rdd)
        return self.from_rdd_of_dataframes(result_rdd)

    def to_spark_sql(self):
        """Returns the underlying SchemaRDD"""
        return self._rdd

    def from_rdd_of_dataframes(self, rdd):
        """A Sparkling Pandas specific function to turn a DDF into
        something that Spark SQL can query. To use the result you will
        need to call sqlCtx.inferSchema(rdd) and then register the result
        as a table. Once Spark 1.1 is released this function may be deprecated
        and replacted with to_spark_sql_schema_rdd."""
        def frame_to_spark_sql(frame):
            """Convert a Panda's DataFrame into Spark SQL Rows"""
            return map((lambda x: x[1].to_dict()), frame.iterrows())
        self._rdd = rdd.flatMap(frame_to_spark_sql)

    def applymap(self, f, **kwargs):
        """Return a new PRDD by applying a function to each element of each
        Panda DataFrame."""
        return self.__evil_apply_with_dataframes(
            lambda rdd: rdd.map(lambda data: data.applymap(f), **kwargs))

    def __getitem__(self, key):
        """Returns a new PRDD of elements from that key."""
        return self.__evil_apply_with_dataframes(
            lambda rdd: rdd.map(lambda x: x[key]))

    def groupby(self, *args, **kwargs):
        """Takes the same parameters as groupby on DataFrame.
        Like with groupby on DataFrame disabling sorting will result in an
        even larger performance improvement. This returns a Sparkling Pandas
        L{GroupBy} object which supports many of the same operations as regular
        GroupBy but not all."""
        from sparklingpandas.groupby import GroupBy
        return GroupBy(self.to_rdd_of_dataframes(), *args, **kwargs)

    @property
    def dtypes(self):
        """
        Return the dtypes associated with this object
        Uses the types from the first frame.
        """
        return self.to_rdd_of_dataframes().first().dtypes

    @property
    def ftypes(self):
        """
        Return the ftypes associated with this object
        Uses the types from the first frame.
        """
        return self.to_rdd_of_dataframes().first().ftypes

    def get_dtype_counts(self):
        """
        Return the counts of dtypes in this object
        Uses the information from the first frame
        """
        return self.to_rdd_of_dataframes().first().get_dtype_counts()

    def get_ftype_counts(self):
        """
        Return the counts of ftypes in this object
        Uses the information from the first frame
        """
        return self.to_rdd_of_dataframes().first().get_ftype_counts()

    @property
    def axes(self):
        return (self.to_rdd_of_dataframes().map(lambda frame: frame.axes)
                .reduce(lambda xy, ab: [xy[0].append(ab[0]), xy[1]]))

    @property
    def shape(self):
        return (self.to_rdd_of_dataframes().map(lambda frame: frame.shape)
                .reduce(lambda xy, ab: (xy[0] + ab[0], xy[1])))

    @property
    def dtypes(self):
        """
        Return the dtypes associated with this object
        Uses the types from the first frame.
        """
        return self.to_rdd_of_dataframes().first().dtypes

    @property
    def ftypes(self):
        """
        Return the ftypes associated with this object
        Uses the types from the first frame.
        """
        return self.to_rdd_of_dataframes().first().ftypes

    def get_dtype_counts(self):
        """
        Return the counts of dtypes in this object
        Uses the information from the first frame
        """
        return self.to_rdd_of_dataframes().first().get_dtype_counts()

    def get_ftype_counts(self):
        """
        Return the counts of ftypes in this object
        Uses the information from the first frame
        """
        return self.to_rdd_of_dataframes().first().get_ftype_counts()

    @property
    def axes(self):
        return (self.to_rdd_of_dataframes().map(lambda frame: frame.axes)
                .reduce(lambda xy, ab: [xy[0].append(ab[0]), xy[1]]))

    @property
    def shape(self):
        return (self.to_rdd_of_dataframes().map(lambda frame: frame.shape)
                .reduce(lambda xy, ab: (xy[0] + ab[0], xy[1])))

    def collect(self):
        """Collect the elements in an PRDD and concatenate the partition."""
        # The order of the frame order appends is based on the implementation
        # of reduce which calls our function with
        # f(valueToBeAdded, accumulator) so we do our reduce implementation.
        def appendFrames(frame_a, frame_b):
            return frame_a.append(frame_b)
        return self.to_rdd_of_dataframes()._custom_rdd_reduce(appendFrames)

    def _custom_rdd_reduce(self, f):
        """Provides a custom RDD reduce which perserves ordering if the RDD has
        been sorted. This is useful for us becuase we need this functionality
        as many panda operations support sorting the results. The standard
        reduce in PySpark does not have this property.  Note that when PySpark
        no longer does partition reduces locally this code will also need to
        be updated."""
        def func(iterator):
            acc = None
            for obj in iterator:
                if acc is None:
                    acc = obj
                else:
                    acc = f(acc, obj)
            if acc is not None:
                yield acc
        vals = self._rdd.mapPartitions(func).collect()
        return reduce(f, vals)

    def stats(self, columns):
        """Compute the stats for each column provided in columns.
        Parameters
        ----------
        columns : list of str, contains all columns to compute stats on.
        """
        def reduceFunc(sc1, sc2):
            return sc1.merge_pstats(sc2)

        return self.to_rdd_of_dataframes().mapPartitions(
            lambda i: [PStatCounter(dataframes=i, columns=columns)]).reduce(
            reduceFunc)

        def reduce_func(sc1, sc2):
            return sc1.merge_pstats(sc2)

        return self._rdd.mapPartitions(
            lambda i: [PStatCounter(dataframes=i, columns=columns)]).reduce(
                reduce_func)
