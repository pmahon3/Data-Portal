package ca.inn.bundler.model;

import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Arrays;

public enum BundleStatus {
    PENDING("pending"),
    PROCESSING("processing"),
    COMPLETE("complete"),
    FAILED("failed");

    private final String value;

    BundleStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    public static BundleStatus fromValue(String value) {
        return Arrays.stream(values())
                .filter(status -> status.value.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unknown bundle status: " + value));
    }

    public boolean canTransitionTo(BundleStatus nextStatus) {
        return switch (this) {
            case PENDING -> nextStatus==PROCESSING || nextStatus==FAILED;
            case PROCESSING -> nextStatus==COMPLETE || nextStatus==FAILED;
            case COMPLETE, FAILED -> false;
        };
    }
}
