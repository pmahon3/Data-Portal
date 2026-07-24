package ca.inn.bundler.model;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class BundleStatusConverter implements AttributeConverter<BundleStatus, String> {
    @Override
    public String convertToDatabaseColumn(BundleStatus status) {
        return status == null ? null : status.getValue();
    }

    @Override
    public BundleStatus convertToEntityAttribute(String value) {
        return value == null ? null : BundleStatus.fromValue(value);
    }
}
