package ca.inn.bundler.exception;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.List;

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(BundleNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleBundleNotFoundException(
            BundleNotFoundException exception,HttpServletRequest request) {
        ErrorResponse body = ErrorResponse.builder()
                .timestamp(Instant.now())
                .status(HttpStatus.NOT_FOUND.value())
                .error(HttpStatus.NOT_FOUND.getReasonPhrase())
                .message(exception.getMessage())
                .path(request.getRequestURI())
                .details(List.of())
                .build();
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);

        }
        //#####################################################
        @ExceptionHandler(MethodArgumentNotValidException.class)
                public ResponseEntity<ErrorResponse>handleValidationError (
                MethodArgumentNotValidException exception,
                HttpServletRequest request){
        List<String> details= exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error-> error.getField() + ": "+ error.getDefaultMessage())
                .toList();
        ErrorResponse body=ErrorResponse.builder()
                .timestamp(Instant.now())
                .status(HttpStatus.BAD_REQUEST.value())
                .error(HttpStatus.BAD_REQUEST.getReasonPhrase())
                .message("Validation failed")
                .path(request.getRequestURI())
                .details(details)
                .build();
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(InvalidBundleStateTransitionException.class)
    public ResponseEntity<ErrorResponse> handleInvalidBundleStateTransition(
            InvalidBundleStateTransitionException exception,
            HttpServletRequest request
    ) {
        ErrorResponse body = ErrorResponse.builder()
                .timestamp(Instant.now())
                .status(HttpStatus.CONFLICT.value())
                .error(HttpStatus.CONFLICT.getReasonPhrase())
                .message(exception.getMessage())
                .path(request.getRequestURI())
                .details(List.of())
                .build();

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }


    //Return 503 (request is valid but service is unavailable
    @ExceptionHandler(BundleQueueFullException.class)
    public ResponseEntity<ErrorResponse>handleBundleQueueFull (
            BundleQueueFullException exception,
            HttpServletRequest request
    ){

        ErrorResponse body = ErrorResponse.builder()
                .timestamp(Instant.now())
                .status(HttpStatus.SERVICE_UNAVAILABLE.value())
                .error(HttpStatus.SERVICE_UNAVAILABLE.getReasonPhrase())
                .message(exception.getMessage())
                .path(request.getRequestURI())
                .details(List.of())
                .build();

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(body);

    }

    @ExceptionHandler(BundleNotReadyException.class)
    public ResponseEntity<ErrorResponse>handleBundleNotReady (
            BundleNotReadyException exception,
            HttpServletRequest request
    ){
        ErrorResponse body= ErrorResponse.builder()
                .timestamp(Instant.now())
                .status(HttpStatus.ACCEPTED.value())
                .error(HttpStatus.ACCEPTED.getReasonPhrase())
                .message(exception.getMessage())
                .path(request.getRequestURI())
                .details(List.of())
                .build();
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(body);
    }

    @ExceptionHandler(BundleFailedException.class)
    public ResponseEntity<ErrorResponse>handleBundleFailed (
            BundleFailedException exception,
            HttpServletRequest request
    ){
        ErrorResponse body= ErrorResponse.builder()
                .timestamp(Instant.now())
                .status(HttpStatus.CONFLICT.value())
                .error(HttpStatus.CONFLICT.getReasonPhrase())
                .message(exception.getMessage())
                .path(request.getRequestURI())
                .details(List.of())
                .build();
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

}
