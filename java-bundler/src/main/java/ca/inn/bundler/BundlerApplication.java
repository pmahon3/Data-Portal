package ca.inn.bundler;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BundlerApplication {

	public static void main(String[] args) {
		SpringApplication.run(BundlerApplication.class, args);
	}

}
