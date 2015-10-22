import inspect
from enum import Enum
from mapper_options import MapperOptions

__author__ = 'lgrech'


class ObjectMapper(object):

    def __init__(self, left_class, right_class, left_prototype_obj=None, right_prototype_obj=None):
        self.__left_class = left_class
        self.__right_class = right_class
        self.__left_prototype_obj = self.__try_get_prototype(left_prototype_obj, self.__left_class)
        self.__right_prototype_obj = self.__try_get_prototype(right_prototype_obj, self.__right_class)
        self.__explicit_mapping_from_left = {}
        self.__explicit_mapping_from_right = {}
        self.__nested_mappers_from_left = {}
        self.__nested_mappers_from_right = {}
        self.__left_initializers = {}
        self.__right_initializers = {}
        self.__general_settings = {}

    @classmethod
    def from_class(cls, left_class, right_class):
        return ObjectMapper(left_class, right_class)

    @classmethod
    def from_prototype(cls, left_proto, right_proto):
        return ObjectMapper(left_proto.__class__, right_proto.__class__, left_proto, right_proto)

    def map(self, obj):

        if isinstance(obj, self.__left_class):
            param_dict = self.__get_mapped_params_dict(
                obj, self.__explicit_mapping_from_left, self.__right_initializers, self.__nested_mappers_from_left,
                self.__right_prototype_obj)

            return self.__try_create_object(self.__right_class, param_dict)

        elif isinstance(obj, self.__right_class):
            param_dict = self.__get_mapped_params_dict(
                obj, self.__explicit_mapping_from_right, self.__left_initializers, self.__nested_mappers_from_right,
                self.__left_prototype_obj)

            return self.__try_create_object(self.__left_class, param_dict)

        else:
            raise ValueError("This mapper does not support {} class".format(obj.__class__.__name__))

    def map_attr_name(self, attr_name):

        if attr_name in self.__explicit_mapping_from_left:
            return self.__explicit_mapping_from_left[attr_name]

        if attr_name in self.__explicit_mapping_from_right:
            return self.__explicit_mapping_from_right[attr_name]

        if self.__left_prototype_obj and self.__right_prototype_obj:
            if hasattr(self.__left_prototype_obj, attr_name) and hasattr(self.__right_prototype_obj, attr_name):
                return attr_name

        raise ValueError(attr_name)

    def custom_mappings(self, mapping_dict):
        mapping_from_left, mapping_from_right = self.__get_explicit_mapping(mapping_dict)
        self.__explicit_mapping_from_left.update(mapping_from_left)
        self.__explicit_mapping_from_right.update(mapping_from_right)
        return self

    def nested_mapper(self, mapper):
        self.__nested_mappers_from_left[mapper.__left_class] = mapper
        self.__nested_mappers_from_right[mapper.__right_class] = mapper
        return self

    def left_initializers(self, initializers_dict):
        self.__left_initializers.update(initializers_dict)
        return self

    def right_initializers(self, initializers_dict):
        self.__right_initializers.update(initializers_dict)
        return self

    def options(self, (setting_name, setting_value)):
        self.__general_settings[setting_name] = setting_value
        return self

    @classmethod
    def __try_create_object(cls, class_, param_dict):
        try:
            return class_(**param_dict)
        except TypeError as er:
            raise AttributeError("Error when initializing class {} with params: {}\n{}".format(
                class_.__name__, param_dict, er.message))

    def __get_mapped_params_dict(self, obj, explicit_mapping, initializers, nested_mappers, prototype_obj):

        actual_mapping = self.__get_actual_mapping(obj, explicit_mapping, prototype_obj)

        mapped_params_dict = {}
        try:
            self.__apply_mapping(mapped_params_dict, obj, actual_mapping, nested_mappers, prototype_obj)
            self.__apply_initializers(mapped_params_dict, obj, initializers)
            return mapped_params_dict
        except AttributeError as er:
            raise AttributeError("Unknown attribute: {}".format(er.message))

    @classmethod
    def __apply_initializers(self, mapped_params_dict, obj, initializers):
        for attr_name, init_func in initializers.items():
            mapped_params_dict[attr_name] = init_func(obj)

    def __apply_mapping(self, mapped_params_dict, obj_from, actual_mapping, nested_mappers, prototype_obj_to):
        for attr_name_from, attr_name_to in actual_mapping.items():

            # skip since mapping is suppressed by user (attribute_name = None)
            if not (attr_name_from and attr_name_to):
                continue

            attr_value = self.__get_attribute_value(obj_from, attr_name_from)

            from_type = type(attr_value)
            to_type = type(self.__get_attribute_value(prototype_obj_to, attr_name_to)) if prototype_obj_to else None

            if from_type in nested_mappers:
                mapped_params_dict[attr_name_to] = nested_mappers[from_type].map(attr_value)
            elif to_type and to_type != from_type:
                mapped_params_dict[attr_name_to] = self.__apply_conversion(from_type, to_type, attr_value)
            else:
                mapped_params_dict[attr_name_to] = attr_value

    @classmethod
    def __apply_conversion(cls, from_type, to_type, attr_value):
        if issubclass(from_type, Enum):
            return cls.__get_conversion_from_enum(attr_value, to_type)
        elif issubclass(to_type, Enum):
            return cls.__get_conversion_to_enum(attr_value, from_type, to_type)
        return attr_value

    @classmethod
    def __get_conversion_to_enum(cls, attr_value, from_type, to_enum_type):
        if from_type == int:
            return to_enum_type(attr_value)
        elif from_type == str:
            # this tries to get enum item from Enum class
            return getattr(to_enum_type, attr_value)
        return attr_value

    @classmethod
    def __get_conversion_from_enum(cls, attr_value, to_type):
        if to_type == int:
            return attr_value.value
        elif to_type == str:
            return attr_value.name
        return attr_value

    def __get_attribute_value(self, obj, attr_name):
        try:
            attr_value = obj[attr_name] if isinstance(obj, dict) else getattr(obj, attr_name)
        except Exception as ex:
            if self.__get_setting(MapperOptions.fail_on_get_attr, True):
                raise ex
            return None

        return attr_value

    @classmethod
    def __get_actual_mapping(cls, obj, explicit_mapping, prototype_obj):

        common_attributes = cls.__get_common_instance_attributes(obj, prototype_obj) if prototype_obj else []

        actual_mapping = {common_attr: common_attr for common_attr in common_attributes}
        actual_mapping.update(explicit_mapping)

        return actual_mapping

    @classmethod
    def __try_get_prototype(cls, prototype_obj, for_class):

        actual_prototype = prototype_obj

        if not actual_prototype:
            actual_prototype = cls.__try_create_prototype(for_class)

        return actual_prototype

    @classmethod
    def __try_create_prototype(cls, to_class):
        try:
            return to_class()
        except TypeError:
            # if we can't instantiate the class then it's not possible to determine instance attributes - implicit
            # mapping won't work
            return None

    @classmethod
    def __get_common_instance_attributes(cls, from_obj, to_obj):
        from_obj_attrs = cls.__get_attributes(from_obj)
        to_obj_attrs = cls.__get_attributes(to_obj)
        return set(from_obj_attrs).intersection(to_obj_attrs)

    @classmethod
    def __get_attributes(cls, obj):

        if isinstance(obj, dict):
            return obj.keys()

        attributes = inspect.getmembers(obj, lambda a: not(inspect.isroutine(a)))
        return [attr[0] for attr in attributes if not(attr[0].startswith('__') and attr[0].endswith('__'))]

    @classmethod
    def __get_explicit_mapping(cls, input_mapping):

        mapping = {}
        rev_mapping = {}

        for left, right in input_mapping.items():
            if right is None:
                # user requested to suppress implicit mapping for k
                mapping[left] = rev_mapping[left] = None
            else:
                mapping[left] = right
                rev_mapping[right] = left

        return mapping, rev_mapping

    def __get_setting(self, mapper_option, default_val):
        if mapper_option.get_name() in self.__general_settings:
            return self.__general_settings[mapper_option.get_name()]

        return default_val
