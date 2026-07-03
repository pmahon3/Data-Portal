package ca.inn.bundler.exception;

public class BundleFailedException extends RuntimeException {
    public BundleFailedException(String bundleId, String errorMessage) {
        super("Bundle failed: " + bundleId + (errorMessage == null || errorMessage.isBlank() ? "" : " - " + errorMessage));
    }
}
