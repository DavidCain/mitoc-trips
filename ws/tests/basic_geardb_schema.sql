-- DROP TABLE if exists `geardb_peopleemails`;
-- DROP TABLE if exists `people_waivers`;
-- DROP TABLE if exists `people_memberships`;
-- DROP TABLE if exists `people`;

CREATE TABLE `people` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `firstname` varchar(100) DEFAULT NULL,
  `lastname` varchar(100) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `password` varchar(128) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `affiliation` varchar(128) DEFAULT NULL,
  `address` varchar(128) DEFAULT NULL,
  `city` varchar(64) DEFAULT NULL,
  `state` varchar(32) DEFAULT NULL,
  `last_login` datetime DEFAULT NULL,
  `last_paid` int(11) NOT NULL DEFAULT '0',
  `date_inserted` datetime DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  `mitoc_credit` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `user_id` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=10174 DEFAULT CHARSET=latin1;

CREATE TABLE `geardb_peopleemails` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `person_id` int(11) NOT NULL,
  `alternate_email` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `alternate_email` (`alternate_email`),
  KEY `geardb_peopleemails_16f39487` (`person_id`),
  CONSTRAINT `person_id_refs_id_8fea2d7b` FOREIGN KEY (`person_id`) REFERENCES `people` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=108 DEFAULT CHARSET=latin1;

CREATE TABLE `people_waivers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `person_id` int(11) DEFAULT NULL,
  `expires` datetime DEFAULT NULL,
  `date_signed` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `person_id` (`person_id`),
  CONSTRAINT `people_waivers_ibfk_1` FOREIGN KEY (`person_id`) REFERENCES `people` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2743572 DEFAULT CHARSET=latin1;

CREATE TABLE `people_memberships` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `person_id` int(11) DEFAULT NULL,
  `membership_type` enum('student','affiliate','general') DEFAULT NULL,
  `price_paid` decimal(6,2) DEFAULT NULL,
  `expires` date DEFAULT NULL,
  `check_number` varchar(16) DEFAULT NULL,
  `date_inserted` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `person_id` (`person_id`),
  CONSTRAINT `people_memberships_ibfk_1` FOREIGN KEY (`person_id`) REFERENCES `people` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=9732 DEFAULT CHARSET=latin1;
