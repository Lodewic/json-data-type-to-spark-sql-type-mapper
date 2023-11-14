import json
from pyspark.sql.types import StructType, StructField, ArrayType, ByteType, ShortType, IntegerType, LongType, FloatType, DoubleType, StringType, BooleanType, TimestampType, DateType, NullType

def from_json_to_spark(schema) -> StructType:
    properties = schema['properties']
    fields = []
    for key, value in properties.items():
        field_type = _map_json_type_to_spark_type(value)
        
        nullable = True
        
        # check whether field is required
        if key in schema.get('required', []):
            nullable = False
        #
        # Setting nullable has no effect on the created DataFrame. This would be needed to be done afterwards.
        #
        # By default, when Spark reads a JSON file and infers the schema, it assumes that all fields are nullable.
        # If the actual data in the file contains null values for a field that was inferred as non-nullable,
        # Spark will coerce that field to be nullable, since it cannot guarantee that the field will always be non-null.
        
        fields.append(StructField(key, field_type, nullable))
    return StructType(fields)


def _map_json_type_to_spark_type(json_snippet): 
    value = json_snippet
    field_type = None 
    if 'type' in json_snippet:
        
        if value['type'] == 'string':
            field_type = _convert_json_string(value)
        elif value['type'] == 'boolean':
            field_type = BooleanType() 
        elif value['type'] == 'integer':
            # This is tricky as there are many Spark types that can be mapped to an int
            field_type = _convert_json_int(value)
        elif value['type'] == 'number':
            # This is also tricky as there are many Spark types that can be mapped to a number
            field_type = _convert_json_number(value)
        elif value['type'] == 'array':
            if 'items' in value:
                items_schemas = value['items']
                
                # An array can have a single type or an array of types
                if isinstance(items_schemas, dict):
                    # put it into list
                    items_schemas = [items_schemas]
                    print("type items_schemas: ", type(items_schemas))
                
                # Check for size
                if len(items_schemas) < 1:
                    raise Exception("Expected a least one type definition in an array")
                
                # Loop over item schemas
                for item_schema in items_schemas:
                    if item_schema['type'] == 'object':
                        field_type = ArrayType(StructType(from_json_to_spark(item_schema).fields))
                    else:
                        field_type = ArrayType(_map_json_type_to_spark_type(item_schema))
                
                # TODO: fix array with multiple types
                
        elif value['type'] == 'object':
            field_type = StructType(from_json_to_spark(value).fields)
        elif value['type'] == 'null':
            field_type = NullType()
        elif value['type'] == 'any':
            field_type = StringType()
        else:
            raise ValueError(f"Invalid JSON type: {value['type']}")
    
    # anyOf is not a type but also a keyword
    elif 'anyOf' in value:
        # A constant can hold all sorts of data types, even complex structures. The savest Spark data type is a StringType.
        field_type = StringType()
    # const is not a type but also a keyword
    elif 'const' in value:
        # A constant can hold all sorts of data types, even complex structures. The savest Spark data type is a StringType.
        field_type = StringType()
        
    return field_type    
    

def _convert_json_string(value):
    field_type =  StringType()
    
    if 'format' in value: # Need to check whether attribute is present first
        if value['format'] == 'date-time':
            field_type = TimestampType()
        elif value['format'] == 'date':
            field_type = DateType()
        
    return field_type
    

def _convert_json_int(value):
    # This is tricky as there are many Spark types that can be mapped to an int
    # 
    # ByteType: Represents 1-byte signed integer numbers. The range of numbers is from -128 to 127.
    # ShortType: Represents 2-byte signed integer numbers. The range of numbers is from -32768 to 32767.
    # IntegerType: Represents 4-byte signed integer numbers. The range of numbers is from -2147483648 to 2147483647.
    # LongType: Represents 8-byte signed integer numbers. The range of numbers is from -9223372036854775808 to 9223372036854775807.
    # 
    # https://spark.apache.org/docs/latest/sql-ref-datatypes.html
    #
    # For instance 20230214110547 fits in a json int, but not in a Spark IntegerType
    #
    field_type = LongType()
    determined_range = _determine_inclusive_range(value)
    if (determined_range["defined"]):
        # max value of range is exclusive              
        byte_type_range = range(-128, 127 + 1)
        short_type_range = range(-32768, 32767 + 1)
        int_type_range = range(-2147483648, 2147483647 + 1)

        if (determined_range["min"] in byte_type_range and determined_range["max"] in byte_type_range):
            field_type = ByteType()
        elif (determined_range["min"] in short_type_range and determined_range["max"] in short_type_range):
            field_type = ShortType()  
        elif (determined_range["min"] in int_type_range and determined_range["max"] in int_type_range):
            field_type = IntegerType()
            
    return field_type

def _convert_json_number(value):
    # This is also tricky as there are many Spark types that can be mapped to a number
    #
    # - FloatType: Represents 4-byte single-precision floating point numbers.
    # - DoubleType: Represents 8-byte double-precision floating point numbers.
    #
    # And optionally
    # - DecimalType: Represents arbitrary-precision signed decimal numbers. Backed internally by java.math.BigDecimal. 
    #   A BigDecimal consists of an arbitrary precision integer unscaled value and a 32-bit integer scale.
    # 
    # https://spark.apache.org/docs/latest/sql-ref-datatypes.html
    #
    #
    field_type = DoubleType()
    # There is no way to know to purpose of the value. To be on the safe side use DoubleType
    return field_type
    
def _determine_inclusive_range(value):
    range = {"min": None, "max": None, "defined": False}
    
    if "minimum" in value:
        range["min"] = int(value["minimum"])
    if "exclusiveMinimum" in value:
        range["min"] = int(value["exclusiveMinimum"]) - 1   
    if "maximum" in value:
        range["max"] = int(value["maximum"])
    if "exclusiveMaximum" in value:
        range["max"] = int(value["exclusiveMaximum"]) - 1

    if range["min"] != None and range["max"] != None:
        range["defined"] = True

    return range